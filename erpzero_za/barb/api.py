"""Asking Barb: the site sends the conversation to Barb's brain at 2nth.ai, runs the tools she asks
for as the signed-in user, and sends back the results until she answers.

The brain never sees the books directly, only the results of tools run here, and never holds
credentials for this site.
"""

import json

import frappe
import requests

from erpzero_za.barb import tools
from erpzero_za.showcase import guests

MAX_STEPS = 10
MAX_TOOL_RESULT = 15000
TIMEOUT = 120


@frappe.whitelist()
def status():
	settings = frappe.get_cached_doc("Barb Settings")
	return {
		"enabled": bool(settings.enabled and settings.barb_url and settings.get_password("barb_key", raise_exception=False)),
		"demo_guest": guests.is_guest(),
		"questions_left": guests.questions_left(),
	}


@frappe.whitelist(methods=["POST"])
def ask(question, history=None, doctype=None, docname=None):
	"""Start a run in the background; the answer arrives over realtime as event "barb"."""
	if not status()["enabled"]:
		frappe.throw("Barb isn't switched on for this site. A System Manager can turn her on in Barb Settings.")
	question = (question or "").strip()[:4000]
	if not question:
		frappe.throw("Ask Barb a question.")
	if guests.questions_left() == 0:
		frappe.throw("That's today's questions for the demo used up. Come back tomorrow, or ask us about Barb for your own books.")
	history = frappe.parse_json(history) if isinstance(history, str) else (history or [])

	log = frappe.get_doc(
		{
			"doctype": "Barb Log",
			"user": frappe.session.user,
			"status": "Running",
			"question": question,
			"company": frappe.defaults.get_user_default("Company"),
			"context_doctype": doctype if doctype in tools.DOCTYPES else None,
			"context_name": docname if doctype in tools.DOCTYPES else None,
		}
	).insert(ignore_permissions=True)
	frappe.enqueue(
		"erpzero_za.barb.api.run",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		log=log.name,
		question=question,
		history=_text_only(history)[-12:],
		doctype=log.context_doctype,
		docname=log.context_name,
	)
	return log.name


def run(log, question, history, doctype=None, docname=None):
	messages = [*history, {"role": "user", "content": question}]
	context = {
		"site": frappe.local.site,
		"user": frappe.session.user,
		"today": frappe.utils.today(),
		"open_doctype": doctype,
		"open_document": docname,
	}
	called, tokens_in, tokens_out, model, steps = [], 0, 0, None, 0
	try:
		answer = None
		for steps in range(1, MAX_STEPS + 1):
			reply = turn(messages, context)
			model = reply.get("model") or model
			tokens_in += reply.get("usage", {}).get("in", 0)
			tokens_out += reply.get("usage", {}).get("out", 0)
			message = reply["message"]
			messages.append({"role": "assistant", **message})
			calls = message.get("tool_calls") or []
			if not calls:
				answer = message.get("content") or ""
				break
			for c in calls:
				name = c["function"]["name"]
				called.append(name)
				_publish(log, "working", tool=name)
				result = tools.call(name, _args(c["function"].get("arguments")))
				# a failed tool leaves nothing half-written; a draft that worked is kept
				if isinstance(result, dict) and result.get("error"):
					frappe.db.rollback()
				else:
					frappe.db.commit()
				messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, default=str)[:MAX_TOOL_RESULT]})
		if answer is None:
			answer = "I ran out of steps before I could finish. Try a narrower question."
		_finish(log, "Done", answer=answer, called=called, model=model, steps=steps, tokens=(tokens_in, tokens_out))
		_publish(log, "done", answer=answer)
	except Exception as e:
		# tools roll back their own failures above; a failed call to Barb's service writes nothing
		message = _friendly(e)
		_finish(log, "Failed", error=message, called=called, model=model, steps=steps, tokens=(tokens_in, tokens_out))
		_publish(log, "failed", error=message)


def turn(messages, context):
	"""One step of Barb's brain: send the conversation, get back an answer or tool calls."""
	settings = frappe.get_cached_doc("Barb Settings")
	response = requests.post(
		settings.barb_url.rstrip("/") + "/v1/turn",
		json={"messages": messages, "context": context, "job": "chat"},
		headers={"Authorization": f"Bearer {settings.get_password('barb_key')}", "User-Agent": "erpzero_za"},
		timeout=TIMEOUT,
	)
	if response.status_code != 200:
		try:
			detail = response.json().get("error")
		except ValueError:
			detail = response.text[:200]
		raise BarbError(f"Barb's service answered {response.status_code}: {detail}")
	return response.json()


class BarbError(Exception):
	pass


def _finish(log, status, answer=None, error=None, called=(), model=None, steps=0, tokens=(0, 0)):
	frappe.db.set_value(
		"Barb Log",
		log,
		{
			"status": status,
			"answer": answer,
			"error": error,
			"tools_called": ", ".join(called),
			"model": model,
			"steps": steps,
			"tokens_in": tokens[0],
			"tokens_out": tokens[1],
		},
		update_modified=True,
	)
	frappe.db.commit()


def _publish(log, state, **data):
	frappe.publish_realtime("barb", {"log": log, "state": state, **data}, user=frappe.session.user)


def _args(arguments):
	if isinstance(arguments, dict):
		return arguments
	try:
		return json.loads(arguments or "{}")
	except ValueError:
		return {}


def _text_only(history):
	return [
		{"role": m["role"], "content": str(m["content"])[:4000]}
		for m in history
		if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
	]


def _friendly(e):
	if isinstance(e, BarbError):
		return str(e)
	if isinstance(e, requests.Timeout):
		return "Barb took too long to answer. Try again in a moment."
	if isinstance(e, requests.RequestException):
		return "Couldn't reach Barb's service. Check the Barb URL in Barb Settings."
	frappe.log_error(title="Barb run failed")
	return f"Something went wrong ({type(e).__name__}). It has been logged."
