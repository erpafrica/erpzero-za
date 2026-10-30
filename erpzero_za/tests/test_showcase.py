from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from erpzero_za.showcase import guests

EMAIL = "lead@example.co.za"


class TestShowcase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name")[0]
		s = frappe.get_single("Showcase Settings")
		s.update({"enabled": 1, "company": cls.company, "lead_email": "sales@example.com", "questions_per_day": 3})
		s.save()

	def tearDown(self):
		frappe.set_user("Administrator")

	def sign_up(self, consent=1):
		with patch.object(guests, "_mail") as mail:
			frappe.local.request_ip = "127.0.0.1"
			guests._make_guest(EMAIL, "Thandi Nkosi", guests.settings())
			lead = guests._record_lead(EMAIL, "Thandi Nkosi", "Nkosi Trading", consent, guests.settings())
			guests._send_link(EMAIL, "Thandi Nkosi", guests.settings())
		return lead, mail

	def test_sign_up_makes_a_guest_limited_to_the_demo_company(self):
		lead, mail = self.sign_up()
		self.assertTrue(guests.is_guest(EMAIL))
		for role in guests.WORK_ROLES:
			self.assertIn(role, frappe.get_roles(EMAIL))
		self.assertNotIn("System Manager", frappe.get_roles(EMAIL))
		self.assertTrue(frappe.db.exists("User Permission", {"user": EMAIL, "allow": "Company", "for_value": self.company}))
		self.assertEqual(lead.marketing_consent, 1)
		self.assertEqual(str(lead.expires_on), add_days(today(), 7))
		link = mail.call_args.args[3]
		self.assertIn("login_via_key", link)

	def test_a_real_user_is_never_made_a_guest(self):
		real = "bookkeeper@example.co.za"
		if not frappe.db.exists("User", real):
			frappe.get_doc({"doctype": "User", "email": real, "first_name": "Real", "send_welcome_email": 0}).insert()
		with patch.object(guests, "_mail") as mail:
			answer = guests.sign_up("Pretender", real)
		self.assertTrue(answer["ok"])
		self.assertFalse(guests.is_guest(real))
		mail.assert_not_called()

	def test_sign_up_emails_the_lead_to_us(self):
		frappe.local.request_ip = "127.0.0.1"
		with patch.object(guests, "_mail"), patch("frappe.sendmail") as sendmail:
			guests.sign_up("Sipho Dlamini", "sipho@example.co.za", "Dlamini Motors", consent=0)
		to_us = sendmail.call_args.kwargs
		self.assertEqual(to_us["recipients"], ["sales@example.com"])
		self.assertEqual(to_us["reply_to"], "sipho@example.co.za")
		self.assertIn("Dlamini Motors", to_us["subject"])
		self.assertIn("one-to-one follow-up only", to_us["message"])
		self.assertTrue(guests.is_guest("sipho@example.co.za"))

	def test_guest_cannot_submit_cancel_or_send(self):
		self.sign_up()
		frappe.set_user(EMAIL)
		doc = frappe._dict(owner="Administrator", docstatus=1)
		with self.assertRaisesRegex(frappe.ValidationError, "submitting is switched off"):
			guests.block_submit(doc)
		with self.assertRaisesRegex(frappe.ValidationError, "cancelling"):
			guests.block_cancel(doc)
		with self.assertRaisesRegex(frappe.ValidationError, "only delete drafts you made"):
			guests.block_delete(doc)
		guests.block_delete(frappe._dict(owner=EMAIL, docstatus=0))  # their own draft is fine
		with self.assertRaisesRegex(frappe.ValidationError, "sending email"):
			guests.block_email(frappe._dict(communication_type="Communication", sent_or_received="Sent"))

	def test_others_are_not_blocked(self):
		guests.setup()  # the Demo Guest role exists, and Administrator holds every role
		self.assertFalse(guests.is_guest("Administrator"))
		guests.block_submit(frappe._dict(owner="Administrator", docstatus=1))
		self.assertIsNone(guests.questions_left())

	def test_question_limit(self):
		self.sign_up()
		self.assertEqual(guests.questions_left(EMAIL), 3)
		for _ in range(3):
			frappe.get_doc({"doctype": "Barb Log", "user": EMAIL, "status": "Done", "question": "Hi"}).insert(ignore_permissions=True)
		self.assertEqual(guests.questions_left(EMAIL), 0)

	def test_nightly_clears_guest_work_and_closes_old_accounts(self):
		self.sign_up()
		frappe.set_user(EMAIL)
		todo = frappe.get_doc({"doctype": "ToDo", "description": "Guest note"}).insert()
		frappe.set_user("Administrator")
		mine = frappe.get_doc({"doctype": "ToDo", "description": "Admin note"}).insert()
		frappe.db.set_value("Showcase Lead", EMAIL, "expires_on", add_days(today(), -1))

		guests.nightly()

		self.assertFalse(frappe.db.exists("ToDo", todo.name))
		self.assertTrue(frappe.db.exists("ToDo", mine.name))
		self.assertEqual(frappe.db.get_value("User", EMAIL, "enabled"), 0)
