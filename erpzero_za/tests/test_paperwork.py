import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from frappe.tests import IntegrationTestCase

from erpzero_za.tests.test_vat import make_invoice, make_item, make_party
from erpzero_za.za_books.paperwork import za_invoice


class TestPaperwork(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name")[0]
		frappe.db.set_value("Company", cls.company, "tax_id", "4999999990")
		cls.customer = make_party("Customer", "Paperwork Test Customer")
		cls.item = make_item()

	def sale(self, amount, template="Standard rate 15%"):
		return make_invoice(self.company, "Sales Invoice", self.customer, self.item, amount, template)

	def test_full_tax_invoice_above_r5000(self):
		z = za_invoice(self.sale(6000))
		self.assertEqual((z.title, z.kind, z.vat_label), ("Tax Invoice", "full", "15%"))
		self.assertEqual((z.subtotal, z.vat, z.total), (6000, 900, 6900))
		self.assertEqual(z.supplier.vat, "4999999990")
		self.assertTrue(any("s20(4)" in n for n in z.notes))  # the customer has no VAT number on record

	def test_abridged_up_to_r5000(self):
		z = za_invoice(self.sale(1000))
		self.assertEqual((z.title, z.kind), ("Tax Invoice", "abridged"))
		self.assertFalse(any("s20(4)" in n for n in z.notes))

	def test_exempt_only_is_not_a_tax_invoice(self):
		z = za_invoice(self.sale(4500, "Exempt"))
		self.assertEqual((z.title, z.vat_label, z.vat), ("Invoice", "Exempt", 0))
		self.assertIn("s12", z.notes[0])

	def test_export_says_why_it_is_zero_rated(self):
		z = za_invoice(self.sale(18000, "Exports 0%"))
		self.assertEqual((z.title, z.vat_label), ("Tax Invoice", "0%"))
		self.assertIn("s11(1)(a)", z.notes[0])

	def test_credit_note_quotes_the_original_invoice(self):
		original = self.sale(2000)
		ret = make_sales_return(original.name)
		ret.remarks = "Two kettles returned chipped"
		ret.insert()
		ret.submit()
		z = za_invoice(ret)
		self.assertEqual(z.title, "Credit Note")
		self.assertEqual(z.original.number, original.name)
		self.assertEqual((z.subtotal, z.vat, z.total), (2000, 300, 2300))  # shown as positive amounts
		self.assertEqual(z.reason, "Two kettles returned chipped")
		self.assertIsNone(z.bank)

	def test_printed_pages(self):
		inv = self.sale(6000)
		html = frappe.get_print("Sales Invoice", inv.name, print_format="ZA Tax Invoice")
		for text in ("Tax Invoice", inv.name, "4999999990", "Payment Advice", "TOTAL VAT 15%"):
			self.assertIn(text, html)
		ret = make_sales_return(inv.name)
		ret.insert()
		ret.submit()
		html = frappe.get_print("Sales Invoice", ret.name, print_format="ZA Tax Invoice")
		self.assertIn("Credit Note", html)
		self.assertIn("Against Invoice", html)
		self.assertNotIn("Payment Advice", html)

	def test_default_print_format(self):
		self.assertEqual(frappe.get_meta("Sales Invoice").default_print_format, "ZA Tax Invoice")
