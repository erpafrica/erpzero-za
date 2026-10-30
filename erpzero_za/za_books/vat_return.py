"""Fixes to csf_za's Value-added Tax Return, kept here until they are accepted upstream.

1. Zero-rated, export and exempt sales (VAT201 fields 2, 2A and 3) post nothing to the VAT
   account, so a return built from the VAT account's ledger never sees them. They are added here
   from the submitted Sales Invoices that used those templates, at their net amount.
2. csf_za's settings map for fields 1A, 2 and 2A has a trailing space in the classification, which
   matches neither the return's totals nor the Select options, so saving a return with any of
   those transactions fails. Classifications are trimmed.
3. Returns are named "{company}-{tax_period}" but nothing set the tax period, so every return of a
   company got the same name. It is set from the period's last month (CCYYMM, SARS's tax period).

fill_from_books() is what the form's "Get transactions" button does, for code and for Barb.
"""

import frappe
from csf_za.tax_compliance.doctype.value_added_tax_return.value_added_tax_return import (
	ValueaddedTaxReturn,
)
from csf_za.tax_compliance.doctype.value_added_tax_return_settings.value_added_tax_return_settings import (
	VAT_RETURN_SETTING_FIELD_MAP,
)

NO_VAT_FIELDS = ("zero_rate_non_exported", "zero_rate_exported", "exempt")

# VAT201 field number → Value-added Tax Return field (SARS GEN-ELEC-04-G01)
VAT201_FIELDS = {
	"1": "standard_rate_main_excl",
	"1A": "standard_rate_capital_excl",
	"2": "zero_rate_main_excl",
	"2A": "zero_rate_exported_excl",
	"3": "exempt_excl",
	"4": "standard_rate_main_incl",
	"4A": "stardard_rate_total",
	"5": "acc_exceed_28_days",
	"6": "acc_exceed_28_days_total",
	"7": "acc_not_exceed_28_days",
	"8": "acc_total_excl",
	"9": "acc_total_incl",
	"10": "adj_change_in_use_excl",
	"11": "adj_change_in_use_incl",
	"12": "adj_other_incl",
	"13": "total_output_tax",
	"14": "capital_goods_supplied",
	"14A": "capital_goods_imported",
	"15": "other_goods_supplied",
	"15A": "other_goods_imported",
	"16": "change_in_use",
	"17": "bad_debts",
	"18": "other",
	"19": "total_input_tax",
	"20": "total_vat_payable_refundable",
}


class ValueaddedTaxReturnZA(ValueaddedTaxReturn):
	def before_insert(self):
		if not self.tax_period and self.date_to:
			self.tax_period = frappe.utils.getdate(self.date_to).strftime("%Y%m")

	def fill_from_books(self):
		self.set("gl_entries", [])
		for entry in self.get_gl_entries():
			self.append(
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
