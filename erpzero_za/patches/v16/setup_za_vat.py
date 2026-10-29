import frappe

from erpzero_za.za_books import vat


def execute():
	# Companies created before the app set up SA VAT on save.
	for company in frappe.get_all("Company", filters={"country": "South Africa"}, pluck="name"):
		if not frappe.db.exists("Value-added Tax Return Settings", company):
			vat.setup_company(company)
