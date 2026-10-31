from datetime import date

import frappe
from frappe.tests import IntegrationTestCase

from erpzero_za.showcase import seed
from erpzero_za.za_books import vat

FROM, TO = date(2026, 3, 1), date(2026, 5, 26)  # covers the Mar–Apr VAT period and its payment on 25 May


class TestDemoYear(IntegrationTestCase):
	"""The demo year is only worth showing a bookkeeper if its books are right: these are the checks."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name")[0]
		seed.run(cls.company, FROM, TO)
		cls.counts = cls.count()

	@classmethod
	def count(cls):
		return {dt: frappe.db.count(dt, {"company": cls.company, "docstatus": 1})
			for dt in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry", "Value-added Tax Return")}

	def test_a_business_traded(self):
		self.assertGreater(self.counts["Sales Invoice"], 60)
		self.assertGreater(self.counts["Purchase Invoice"], 20)
		self.assertGreater(self.counts["Payment Entry"], 60)
		self.assertTrue(frappe.db.exists("Sales Invoice", {"company": self.company, "is_return": 1, "docstatus": 1}))

	def test_running_again_creates_nothing(self):
		seed.run(self.company, FROM, TO)
		self.assertEqual(self.count(), self.counts)

	def test_vat201_agrees_with_the_vat_account(self):
		ret = frappe.get_doc("Value-added Tax Return", {"company": self.company, "date_from": date(2026, 3, 1), "date_to": date(2026, 4, 30)})
		self.assertEqual(ret.docstatus, 1)
		(ledger,) = frappe.db.sql(
			"""select coalesce(sum(credit - debit), 0) from `tabGL Entry`
			where account = %s and posting_date between %s and %s and is_cancelled = 0
			and voucher_type in ('Sales Invoice', 'Purchase Invoice')""",
			(vat.get_vat_account(self.company), ret.date_from, ret.date_to),
		)[0]
		self.assertAlmostEqual(ret.total_vat_payable_refundable, ledger, places=2)
		self.assertGreater(ret.zero_rate_exported_excl + ret.exempt_excl, 0)  # exports and the cottage rent are on it

	def test_vat_paid_to_sars_on_the_25th(self):
		ret = frappe.get_doc("Value-added Tax Return", {"company": self.company, "date_to": date(2026, 4, 30)})
		je = frappe.get_doc("Journal Entry", {"company": self.company, "cheque_no": "KK-202604-VAT"})
		self.assertEqual(str(je.posting_date), "2026-05-25")
		self.assertAlmostEqual(je.total_debit, abs(ret.total_vat_payable_refundable), places=2)

	def test_payroll_and_emp201(self):
		for ref in ("KK-202603-PAY", "KK-202604-PAY", "KK-202604-EMP201", "KK-202605-EMP201"):
			self.assertTrue(frappe.db.exists("Journal Entry", {"company": self.company, "cheque_no": ref, "docstatus": 1}), ref)
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		(paye,) = frappe.db.sql("select coalesce(sum(credit - debit), 0) from `tabGL Entry` where account = %s and is_cancelled = 0 and posting_date <= %s",
			(f"PAYE Payable - {abbr}", TO))[0]
		self.assertEqual(paye, seed.PAYROLL["paye"])  # April's PAYE is owed until the June EMP201

	def test_customers_pay_on_their_habits(self):
		def outstanding(customer):
			return frappe.db.sql("select coalesce(sum(outstanding_amount), 0) from `tabSales Invoice` where customer = %s and docstatus = 1 and company = %s and posting_date < '2026-04-01'",
				(customer, self.company))[0][0]
		self.assertEqual(outstanding("Karoo Padstal (Pty) Ltd"), 0)  # prompt payer: March invoices paid by late May
		part = frappe.get_all("Payment Entry Reference", filters={"reference_doctype": "Sales Invoice", "docstatus": 1},
			fields=["reference_name", "allocated_amount", "total_amount"])
		self.assertTrue(any(r.allocated_amount < r.total_amount for r in part))  # someone paid in part

	def test_suppliers_paid_and_debit_orders_same_day(self):
		fnb = frappe.get_all("Purchase Invoice", filters={"company": self.company, "supplier": "FNB", "docstatus": 1}, fields=["outstanding_amount"])
		self.assertTrue(fnb)
		self.assertTrue(all(r.outstanding_amount == 0 for r in fnb))
