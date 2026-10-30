"""Showcase mode: visitors try the books as a Demo Guest.

A visitor leaves their name and email on the website and gets a one-time sign-in link, so every
lead has a working address. The guest gets the ordinary Accounts, Sales and Purchase User roles,
limited to the demo company, so every screen works as it would for a real bookkeeper. The Demo
Guest role then switches off anything that could do damage: submitting, cancelling, deleting
someone else's records and sending email. Each night their drafts are cleared, and after a week
the account is switched off.
"""

import re

import frappe
from frappe.permissions import add_user_permission
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, now_datetime, today, validate_email_address
from frappe.www.login import _generate_temporary_login_link

ROLE = "Demo Guest"
WORK_ROLES = ("Accounts User", "Sales User", "Purchase User")
CLEARED_EACH_NIGHT = (
	"Value-added Tax Return",
	"Sales Invoice",
	"Purchase Invoice",
	"Quotation",
	"Sales Order",
	"Purchase Order",
	"Journal Entry",
	"Payment Entry",
	"Customer",
	"Supplier",
	"Item",
	"Address",
	"Contact",
	"ToDo",
	"File",
)


def settings():
	return frappe.get_cached_doc("Showcase Settings")


def is_guest(user=None):
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):  # Administrator holds every role, Demo Guest included
		return False
	return ROLE in frappe.get_roles(user)


def setup():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	frappe.db.set_single_value("System Settings", "login_with_email_link", 1)


# ---------- sign-up ----------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def signup(full_name, email, company_name=None, consent=0, website=None):
	"""Called by the demo page's form (five sign-ups an hour per address)."""
	return sign_up(full_name, email, company_name, consent, website)


def sign_up(full_name, email, company_name=None, consent=0, website=None):
	"""Always answers the same way, so the form can't be used to find out who has an account."""
	s = settings()
	if not s.enabled:
		frappe.throw("The demo isn't open just now.")
	answer = {"ok": True, "message": "Check your inbox: we've sent you a sign-in link."}
	if website:  # a field people can't see; bots fill it in
		return answer

	email = (email or "").strip().lower()
	full_name = re.sub(r"\s+", " ", (full_name or "").strip())[:140]
	if not validate_email_address(email) or not full_name:
		frappe.throw("Please give your name and a valid email address.")
	if frappe.db.exists("User", email) and not is_guest(email):
		return answer  # a real user of this site: never turn them into a guest

	_make_guest(email, full_name, s)
	lead = _record_lead(email, full_name, company_name, frappe.utils.cint(consent), s)
	frappe.db.commit()
	_send_link(email, full_name, s)
	if s.lead_email:
		_tell_us(lead, s)
	return answer


def _record_lead(email, full_name, company_name, consent, s):
	lead = frappe.get_doc("Showcase Lead", email) if frappe.db.exists("Showcase Lead", email) else frappe.new_doc("Showcase Lead")
	lead.update(
		{
			"email": email,
			"full_name": full_name,
			"company_name": (company_name or "").strip()[:140] or lead.company_name,
			"user": email,
			"expires_on": add_days(today(), s.guest_days or 7),
			"sign_up_count": (lead.sign_up_count or 0) + 1,
			"last_sign_up": now_datetime(),
			"ip_address": frappe.local.request_ip,
		}
	)
	if consent:  # consent only ever moves to yes here; opting out is done by a person
		lead.marketing_consent, lead.consent_text = 1, s.consent_text
	lead.save(ignore_permissions=True)
	return lead


def _make_guest(email, full_name, s):
	first, _, last = full_name.partition(" ")
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
	else:
		user = frappe.new_doc("User")
		user.update({"email": email, "first_name": first, "last_name": last, "send_welcome_email": 0, "user_type": "System User"})
	if frappe.db.has_column("User", "default_workspace") and frappe.db.exists("Workspace", "Accounting"):
		user.default_workspace = "Accounting"
	user.flags.ignore_permissions = True
	user.save()
	user.add_roles(ROLE, *WORK_ROLES)
	if not frappe.db.exists("User Permission", {"user": email, "allow": "Company", "for_value": s.company}):
		add_user_permission("Company", s.company, email, ignore_permissions=True, is_default=1)


def _send_link(email, full_name, s):
	minutes = s.link_minutes or 60
	link = _generate_temporary_login_link(email, minutes)
	try:
		_mail(email, full_name, s, link, minutes)
	except Exception:
		frappe.log_error(title="Demo sign-in link not sent")
		frappe.throw("We couldn't send the sign-in email just now. Please try again in a few minutes.")


def _mail(email, full_name, s, link, minutes):
	frappe.sendmail(
		recipients=[email],
		subject="Your sign-in link for the Karoo Kettle demo",
		message=frappe.render_template(
			"templates/emails/demo_sign_in.html",
			{
				"first_name": full_name.split(" ")[0],
				"link": link,
				"minutes": minutes,
				"days": s.guest_days or 7,
				"company": s.company,
				"barb": "barb" in frappe.get_installed_apps(),
			},
		),
		now=True,
	)


def _tell_us(lead, s):
	"""Send the lead to whoever follows up (Showcase Settings → Send leads to)."""
	rows = [
		("Name", lead.full_name),
		("Email", lead.email),
		("Company", lead.company_name or "–"),
		("Marketing email", "Yes: " + (lead.consent_text or "") if lead.marketing_consent else "Not agreed (one-to-one follow-up only)"),
		("Sign-ups", lead.sign_up_count),
		("Demo", f"{s.company} on {frappe.local.site}"),
	]
	try:
		frappe.sendmail(
			recipients=[s.lead_email],
			reply_to=lead.email,
			subject=f"Demo sign-up: {lead.full_name}" + (f", {lead.company_name}" if lead.company_name else ""),
			message="<table>" + "".join(f"<tr><td><b>{k}</b></td><td>{frappe.utils.escape_html(str(v))}</td></tr>" for k, v in rows) + "</table>"
			+ "<p>What they ask Barb is in Barb Log, filtered by their email.</p>",
		)
		lead.db_set("lead_sent", now_datetime())
	except Exception:
		frappe.log_error(title="Demo lead email not sent")


# ---------- guard rails (doc_events and permission hooks) ----------


def block_submit(doc, method=None):
	if is_guest():
		frappe.throw("This is a demo: you can prepare drafts, but submitting is switched off.", title="Demo")


def block_cancel(doc, method=None):
	if is_guest():
		frappe.throw("This is a demo: cancelling is switched off.", title="Demo")


def block_delete(doc, method=None):
	if is_guest() and (doc.owner != frappe.session.user or doc.get("docstatus")):
		frappe.throw("This is a demo: you can only delete drafts you made.", title="Demo")


def block_email(doc, method=None):
	if is_guest() and doc.communication_type == "Communication" and doc.sent_or_received == "Sent":
		frappe.throw("This is a demo: sending email is switched off.", title="Demo")


def questions_left(user=None):
	"""Barb questions a Demo Guest has left today; None for everyone else."""
	if not is_guest(user) or not frappe.db.exists("DocType", "Barb Log"):
		return None
	asked = frappe.db.count("Barb Log", {"user": user or frappe.session.user, "creation": (">=", today())})
	return max(0, (settings().questions_per_day or 20) - asked)


# ---------- each night ----------


def nightly():
	"""Clear what guests made, and switch off guests whose week is up."""
	if not frappe.db.exists("Role", ROLE):
		return
	guests = frappe.get_all("Has Role", filters={"role": ROLE, "parenttype": "User"}, pluck="parent")
	for doctype in CLEARED_EACH_NIGHT:
		meta = frappe.get_meta(doctype)
		filters = {"owner": ("in", guests)} if guests else None
		if not filters:
			break
		if meta.is_submittable:
			filters["docstatus"] = 0
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			try:
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
			except Exception:
				frappe.db.rollback()  # still linked from something; tomorrow's run tries again
			else:
				frappe.db.commit()

	for lead in frappe.get_all("Showcase Lead", filters={"expires_on": ("<", today())}, fields=["user"]):
		if lead.user and is_guest(lead.user):
			frappe.db.set_value("User", lead.user, "enabled", 0)
	frappe.db.commit()
