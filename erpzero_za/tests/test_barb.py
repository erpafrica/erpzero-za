import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_first_day, get_last_day, today

from erpzero_za.barb import api, tools
from erpzero_za.tests.test_vat import make_invoice, make_item, make_party


class TestBarbTools(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name")[0]

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_only_the_books(self):
		self.assertIn("error", tools.call("list_documents", {"doctype": "User"}))
		self.assertIn("error", tools.call("run_report", {"report": "Permitted Documents For User"}))
		self.assertIn("error", tools.call("no_such_tool", {}))

	def test_runs_with_the_users_permissions(self):
		frappe.set_user("Guest")
		result = tools.call("list_documents", {"doctype": "Sales Invoice"})
		self.assertIn("permission", result["error"])

	def test_context(self):
		result = tools.call("context", {})
		self.assertIn(self.company, [c["name"] for c in result["companies"]])
		self.assertEqual(result["today"], today())

	def test_vat_return_is_a_draft_by_sars_field(self):
		make_invoice(self.company, "Sales Invoice", make_party("Customer", "VAT Test Customer"), make_item(), 1000, "Standard rate 15%")

		result = tools.call(
			"vat_return",
			{"company": self.company, "date_from": str(get_first_day(today())), "date_to": str(get_last_day(today()))},
		)
		self.assertEqual(result["status"], "Draft")
		self.assertGreaterEqual(result["vat201"]["1"], 1150)
		self.assertGreaterEqual(result["vat201"]["4"], 150)
		self.assertEqual(frappe.db.get_value("Value-added Tax Return", result["return"], "docstatus"), 0)


class TestBarbLoop(IntegrationTestCase):
	def test_runs_tools_then_answers(self):
		replies = iter(
			[
				{"model": "test", "usage": {"in": 10, "out": 5}, "message": {"content": None, "tool_calls": [
					{"id": "c1", "type": "function", "function": {"name": "context", "arguments": "{}"}}]}},
				{"model": "test", "usage": {"in": 20, "out": 7}, "message": {"content": "You have one company."}},
			]
		)
		sent = []

		def fake_turn(messages, context):
			sent.append([dict(m) for m in messages])
			return next(replies)

		log = frappe.get_doc({"doctype": "Barb Log", "user": "Administrator", "status": "Running", "question": "What companies?"}).insert()
		with patch.object(api, "turn", fake_turn):
			api.run(log.name, "What companies?", [])

		log.reload()
		self.assertEqual(log.status, "Done")
		self.assertEqual(log.answer, "You have one company.")
		self.assertEqual(log.tools_called, "context")
		self.assertEqual((log.tokens_in, log.tokens_out, log.steps), (30, 12, 2))
		tool_result = json.loads(sent[1][-1]["content"])
		self.assertEqual(sent[1][-1]["role"], "tool")
		self.assertIn("companies", tool_result)

	def test_service_error_is_logged(self):
		def broken(messages, context):
			raise api.BarbError("Barb's service answered 401: bad key")

		log = frappe.get_doc({"doctype": "Barb Log", "user": "Administrator", "status": "Running", "question": "Hi"}).insert()
		with patch.object(api, "turn", broken):
			api.run(log.name, "Hi", [])
		log.reload()
		self.assertEqual(log.status, "Failed")
		self.assertIn("401", log.error)
