"""South African sales paperwork: what goes on a tax invoice or credit note, decided here so the print
format only lays it out (and so the rules can be tested).

Value-Added Tax Act 89 of 1991:
- s20(4) full tax invoice when the consideration is more than R5,000: the words "tax invoice"; the
  supplier's and recipient's names, addresses and VAT numbers; a serial number and date; a full
  description; quantity; and the value, the VAT and the consideration (or the consideration with a
  statement that it includes VAT at the rate).
- s20(5) abridged tax invoice up to R5,000: the recipient's details may be left out.
- s21 credit and debit notes: the words "credit note", both parties, the date, the original tax
  invoice, the reduction and the VAT on it, and a brief reason.
- An invoice for exempt supplies only (s12) carries no VAT and is not a tax invoice.
"""

import frappe
from frappe.utils import flt, formatdate

FULL_INVOICE_ABOVE = 5000
NOTES = {
	"zero_rate_non_exported": "Zero-rated supply (VAT Act s11).",
	"zero_rate_exported": "Zero-rated export of goods (VAT Act s11(1)(a)).",
	"exempt": "Exempt supply (VAT Act s12): no VAT charged.",
}


def za_invoice(doc):
	"""Everything the ZA Tax Invoice print format shows, for a Sales Invoice or its credit note."""
	sign = -1 if doc.is_return else 1
	field = _vat_field(doc)
	exempt_only = field == "exempt"
	total = sign * flt(doc.grand_total)
	full = total > FULL_INVOICE_ABOVE or doc.is_return
	rate = sum(flt(t.rate) for t in doc.get("taxes") or [] if t.charge_type == "On Net Total")

	if doc.is_return:
		title = "Credit Note"
	elif exempt_only:
		title = "Invoice"
	else:
		title = "Tax Invoice"

	out = frappe._dict(
		title=title,
		full=full,
		kind="full" if full else "abridged",
		number=doc.name,
		date=formatdate(doc.posting_date, "d MMMM yyyy"),
		due_date=formatdate(doc.due_date, "d MMMM yyyy") if doc.due_date and not doc.is_return else None,
		reference=doc.po_no,
		currency=doc.currency,
		supplier=_party(doc.company, doc.company_address_display, doc.get("company_tax_id")
			or frappe.get_cached_value("Company", doc.company, "tax_id")),
		recipient=_party(doc.customer_name, doc.address_display, doc.tax_id),
		vat_label="Exempt" if exempt_only else f"{rate:g}%",
		lines=[
			frappe._dict(
				description=(i.description or i.item_name or "").strip(),
				item_code=i.item_code,
				qty=sign * flt(i.qty),
				uom=i.uom,
				rate=flt(i.rate),
				amount=sign * flt(i.amount),
			)
			for i in doc.items
		],
		subtotal=sign * flt(doc.net_total),
		vat=sign * flt(doc.total_taxes_and_charges),
		total=total,
		amount_due=sign * flt(doc.outstanding_amount) if not doc.is_return else None,
		notes=[NOTES[field]] if field in NOTES else [],
		original=None,
		reason=None,
		bank=_bank(doc.company) if not doc.is_return else None,
	)
	if doc.is_return and doc.return_against:
		orig = frappe.db.get_value("Sales Invoice", doc.return_against, ["name", "posting_date"], as_dict=True)
		out.original = frappe._dict(number=orig.name, date=formatdate(orig.posting_date, "d MMMM yyyy")) if orig else None
		out.reason = (doc.remarks or "").strip() if doc.remarks and doc.remarks != "No Remarks" else None
	if full and not out.recipient.vat and not doc.is_return:
		out.notes.append("Recipient VAT number: not supplied. Required on a full tax invoice if the customer is a VAT vendor (VAT Act s20(4)).")
	return out


def _vat_field(doc):
	"""The VAT201 field this invoice's tax template maps to, from the company's VAT return settings."""
	if not doc.taxes_and_charges or not frappe.db.exists("Value-added Tax Return Settings", doc.company):
		return None
	settings = frappe.get_cached_doc("Value-added Tax Return Settings", doc.company)
	for field in ("standard_rate_non_capital", "standard_rate_capital", "zero_rate_non_exported", "zero_rate_exported", "exempt"):
		if settings.get(field) == doc.taxes_and_charges:
			return field
	return None


def _party(name, address_html, vat):
	lines = [l.strip() for l in (address_html or "").replace("<br>", "\n").replace("<br/>", "\n").splitlines() if l.strip()]
	return frappe._dict(name=name, address=lines, vat=(vat or "").strip() or None)


def _bank(company):
	account = frappe.get_all(
		"Bank Account",
		filters={"company": company, "is_company_account": 1, "disabled": 0},
		fields=["bank", "account_name", "bank_account_no", "branch_code"],
		order_by="is_default desc, creation asc",
		limit=1,
	)
	return account[0] if account else None


def set_default_print_format():
	"""Sales Invoices print as ZA Tax Invoice (credit notes included) unless a site chooses otherwise."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	if frappe.db.exists("Print Format", "ZA Tax Invoice"):
		make_property_setter("Sales Invoice", None, "default_print_format", "ZA Tax Invoice", "Data", for_doctype=True, validate_fields_for_doctype=False)
