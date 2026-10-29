import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe.tests import IntegrationTestCase
from frappe.utils import get_first_day, get_last_day, today

from erpzero_za.za_books import vat
from erpzero_za.za_books.vat_return import ValueaddedTaxReturn


class TestVAT(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name")[0]
		cls.abbr = frappe.get_cached_value("Company", cls.company, "abbr")

	def template(self, title):
		return f"{title} - {self.abbr}"

	def test_company_set_up_on_save(self):
		for title, *_ in vat.SALES_TEMPLATES:
			self.assertTrue(frappe.db.exists(vat.SALES, self.template(title)), title)
		for title, *_ in vat.PURCHASE_TEMPLATES:
			self.assertTrue(frappe.db.exists(vat.PURCHASE, self.template(title)), title)
		self.assertEqual(frappe.db.get_value(vat.SALES, self.template("Standard rate 15%"), "is_default"), 1)

		settings = frappe.get_doc("Value-added Tax Return Settings", self.company)
		self.assertEqual(settings.zero_rate_exported, self.template("Exports 0%"))
		self.assertEqual(settings.input_capital_import, self.template("Capital goods imported 15%"))
		self.assertEqual([r.account for r in settings.tax_accounts], [vat.get_vat_account(self.company)])

	def test_vat201_from_the_books(self):
		"""One invoice per VAT201 field, then the return built by csf_za must show each in its field."""
		item = make_item()
		customer = make_party("Customer", "VAT Test Customer")
		supplier = make_party("Supplier", "VAT Test Supplier")

		self.invoice("Sales Invoice", customer, item, 1000, "Standard rate 15%")  # field 1: 1150 incl, 150 VAT
		self.invoice("Sales Invoice", customer, item, 2000, "Capital goods sold 15%")  # 1A: 2300, 300 VAT
		self.invoice("Sales Invoice", customer, item, 500, "Zero-rated 0%")  # 2
		self.invoice("Sales Invoice", customer, item, 400, "Exports 0%")  # 2A
		self.invoice("Sales Invoice", customer, item, 300, "Exempt")  # 3
		self.invoice("Purchase Invoice", supplier, item, 200, "Standard rate 15%")  # 15: 30 VAT
		self.invoice("Purchase Invoice", supplier, item, 1000, "Capital goods 15%")  # 14: 150 VAT

		ret = frappe.get_doc(
			{
				"doctype": "Value-added Tax Return",
				"company": self.company,
				"date_from": get_first_day(today()),
				"date_to": get_last_day(today()),
			}
		).insert()

		# csf_za on its own still misses no-VAT sales and pads three classifications with a space.
		# When this fails, upstream has fixed them and erpzero_za/za_books/vat_return.py can go.
		upstream = ValueaddedTaxReturn.get_gl_entries(ret)
		self.assertNotIn(self.template("Zero-rated 0%"), {e.taxes_and_charges_template for e in upstream})
		self.assertTrue(any((e.classification or "").endswith(" ") for e in upstream))

		for entry in ret.get_gl_entries():
			ret.append(
				"gl_entries",
				{
					"gl_entry": entry.get("name"),
					"voucher_type": entry.voucher_type,
					"voucher_no": entry.voucher_no,
					"posting_date": entry.posting_date,
					"taxes_and_charges": entry.taxes_and_charges_template,
					"classification": entry.classification,
					"tax_amount": entry.tax_amount,
					"incl_tax_amount": entry.incl_tax_amount,
					"is_cancelled": entry.is_cancelled,
				},
			)
		ret.save()

		self.assertEqual(ret.standard_rate_main_excl, 1150)  # field 1
		self.assertEqual(ret.standard_rate_main_incl, 150)  # field 4
		self.assertEqual(ret.standard_rate_capital_excl, 2300)  # field 1A
		self.assertEqual(ret.stardard_rate_total, 300)  # field 4A
		self.assertEqual(ret.zero_rate_main_excl, 500)  # field 2
		self.assertEqual(ret.zero_rate_exported_excl, 400)  # field 2A
		self.assertEqual(ret.exempt_excl, 300)  # field 3
		self.assertEqual(ret.capital_goods_supplied, 150)  # field 14
		self.assertEqual(ret.other_goods_supplied, 30)  # field 15
		self.assertEqual(ret.total_output_tax, 450)
		self.assertEqual(ret.total_input_tax, 180)
		self.assertEqual(ret.total_vat_payable_refundable, 270)

	def invoice(self, doctype, party, item, amount, title):
		template = self.template(title)
		master = vat.SALES if doctype == "Sales Invoice" else vat.PURCHASE
		doc = frappe.get_doc(
			{
				"doctype": doctype,
				"company": self.company,
				("customer" if doctype == "Sales Invoice" else "supplier"): party,
				"posting_date": today(),
				"set_posting_time": 1,
				"items": [{"item_code": item, "qty": 1, "rate": amount}],
				"taxes_and_charges": template,
				"taxes": get_taxes_and_charges(master, template),
			}
		)
		doc.insert()
		doc.submit()
		return doc


def make_item():
	if not frappe.db.exists("Item", "VAT-TEST-SERVICE"):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "VAT-TEST-SERVICE",
				"item_name": "VAT test service",
				"item_group": "Services",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert()
	return "VAT-TEST-SERVICE"


def make_party(doctype, name):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, f"{doctype.lower()}_name": name}).insert()
	return name
