"""South African VAT set-up for a company: one tax template per VAT201 field, mapped in csf_za's
Value-added Tax Return Settings so the return can be prepared from the books.

Runs when a South African company is saved (the setup wizard creates it) and from a patch for
companies that existed before. It is idempotent: nothing is created twice, and nothing a user has
changed is overwritten.

The VAT201 field names in the comments are SARS's, as printed on the return.
"""

import frappe

SALES = "Sales Taxes and Charges Template"
PURCHASE = "Purchase Taxes and Charges Template"

# (title, rate, csf_za settings field, VAT201 field)
SALES_TEMPLATES = (
	("Standard rate 15%", 15, "standard_rate_non_capital", "1"),
	("Capital goods sold 15%", 15, "standard_rate_capital", "1A"),
	("Zero-rated 0%", 0, "zero_rate_non_exported", "2"),
	("Exports 0%", 0, "zero_rate_exported", "2A"),
	("Exempt", 0, "exempt", "3"),
)
PURCHASE_TEMPLATES = (
	("Standard rate 15%", 15, "input_goods_local", "15"),
	("Capital goods 15%", 15, "input_capital_local", "14"),
	("Imports 15%", 15, "input_goods_import", "15A"),
	("Capital goods imported 15%", 15, "input_capital_import", "14A"),
	("No VAT", 0, None, None),
)
DEFAULT_TITLE = "Standard rate 15%"


def on_company_update(doc, method=None):
	if doc.country != "South Africa" or frappe.db.exists("Value-added Tax Return Settings", doc.name):
		return
	try:
		setup_company(doc.name)
	except Exception:
		# Never block saving a company (or the setup wizard) over VAT set-up; it can be re-run.
		frappe.log_error(title=f"ErpZeroZA: VAT set-up failed for {doc.name}")


def setup_company(company):
	vat_account = get_vat_account(company)
	if not vat_account:
		return

	sales = {t[2]: make_template(SALES, company, t, vat_account) for t in SALES_TEMPLATES}
	purchase = {t[2]: make_template(PURCHASE, company, t, vat_account) for t in PURCHASE_TEMPLATES}
	sales.pop(None, None)
	purchase.pop(None, None)

	disable_wizard_templates(company)
	make_vat_return_settings(company, vat_account, {**sales, **purchase})


def get_vat_account(company):
	"""The company's VAT control account: the one leaf Tax account, as the SA chart and Xero have it."""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": "Tax", "is_group": 0, "disabled": 0},
		pluck="name",
	)
	return accounts[0] if len(accounts) == 1 else None


def make_template(doctype, company, template, vat_account):
	title, rate, _field, vat201_field = template
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{title} - {abbr}"
	if frappe.db.exists(doctype, name):
		return name

	description = f"VAT {rate}%" if rate else f"VAT ({title.lower()})"
	frappe.get_doc(
		{
			"doctype": doctype,
			"title": title,
			"company": company,
			"is_default": int(title == DEFAULT_TITLE),
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": vat_account,
					"rate": rate,
					"description": description + (f" · VAT201 field {vat201_field}" if vat201_field else ""),
				}
			],
		}
	).insert(ignore_permissions=True)
	return name


def disable_wizard_templates(company):
	"""The setup wizard adds a single "South Africa Tax" template; ours replace it."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	for doctype in (SALES, PURCHASE, "Item Tax Template"):
		name = f"South Africa Tax - {abbr}"
		if frappe.db.exists(doctype, name):
			frappe.db.set_value(doctype, name, "disabled", 1)


def make_vat_return_settings(company, vat_account, templates):
	doc = frappe.new_doc("Value-added Tax Return Settings")
	doc.update(
		{
			"company": company,
			"transaction_classification": "Taxes and Charges Templates",
			"output_tax_doctype": SALES,
			"input_tax_doctype": PURCHASE,
			"tax_accounts": [{"account": vat_account}],
			**templates,
		}
	)
	doc.insert(ignore_permissions=True)

