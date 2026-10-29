"""Fixes to csf_za's Value-added Tax Return, kept here until they are accepted upstream.

1. Zero-rated, export and exempt sales (VAT201 fields 2, 2A and 3) post nothing to the VAT
   account, so a return built from the VAT account's ledger never sees them. They are added here
   from the submitted Sales Invoices that used those templates, at their net amount.
2. csf_za's settings map for fields 1A, 2 and 2A has a trailing space in the classification, which
   matches neither the return's totals nor the Select options, so saving a return with any of
   those transactions fails. Classifications are trimmed.
"""

import frappe
from csf_za.tax_compliance.doctype.value_added_tax_return.value_added_tax_return import (
	ValueaddedTaxReturn,
)
from csf_za.tax_compliance.doctype.value_added_tax_return_settings.value_added_tax_return_settings import (
	VAT_RETURN_SETTING_FIELD_MAP,
)

NO_VAT_FIELDS = ("zero_rate_non_exported", "zero_rate_exported", "exempt")


class ValueaddedTaxReturnZA(ValueaddedTaxReturn):
	@frappe.whitelist()
	def get_gl_entries(self):
		entries = super().get_gl_entries()
		seen = {e.get("voucher_no") for e in entries}
		entries += [e for e in self.get_no_vat_sales() if e.voucher_no not in seen]
		for entry in entries:
			if entry.get("classification"):
				entry.classification = entry.classification.strip()
		return entries

	def get_no_vat_sales(self):
		settings = frappe.get_cached_doc("Value-added Tax Return Settings", self.company)
		classification = {
			settings.get(m["field_name"]): m["classification"].strip()
			for m in VAT_RETURN_SETTING_FIELD_MAP
			if m["field_name"] in NO_VAT_FIELDS and settings.get(m["field_name"])
		}
		if not classification:
			return []

		invoices = frappe.get_all(
			"Sales Invoice",
			filters={
				"company": self.company,
				"docstatus": 1,
				"posting_date": ("between", (self.date_from, self.date_to)),
				"taxes_and_charges": ("in", list(classification)),
			},
			fields=["name", "posting_date", "taxes_and_charges", "base_net_total"],
			order_by="posting_date, name",
		)
		return [
			frappe._dict(
				name=None,
				voucher_type="Sales Invoice",
				voucher_no=inv.name,
				posting_date=inv.posting_date,
				taxes_and_charges_template=inv.taxes_and_charges,
				general_ledger_debit=0,
				general_ledger_credit=0,
				classification=classification[inv.taxes_and_charges],
				classification_debugging="ErpZeroZA: no VAT ledger entry for this invoice; amount is its net total",
				tax_amount=0,
				incl_tax_amount=inv.base_net_total,
				is_cancelled=0,
			)
			for inv in invoices
		]
