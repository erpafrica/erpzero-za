"""Barb's hands: the tools her brain (at 2nth.ai) asks this site to run.

Every tool runs as the signed-in user through ERPNext's own permission checks, so Barb sees and
changes only what that person could. Reads are limited to the books; the only write is a draft,
never a submit, cancel or delete.
"""

import json

import frappe
from frappe.desk.query_report import run as run_query_report
from frappe.utils import getdate, today

from erpzero_za.za_books.vat_return import VAT201_FIELDS

DOCTYPES = {
	"Account",
	"Bank Account",
	"Bank Transaction",
	"Company",
	"Cost Center",
	"Customer",
	"Delivery Note",
	"Fiscal Year",
	"GL Entry",
	"Item",
	"Journal Entry",
	"Payment Entry",
	"Purchase Invoice",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Taxes and Charges Template",
	"Quotation",
	"Sales Invoice",
	"Sales Order",
	"Sales Taxes and Charges Template",
	"Supplier",
	"Value-added Tax Return",
}
REPORTS = {
	"Accounts Payable",
	"Accounts Payable Summary",
	"Accounts Receivable",
	"Accounts Receivable Summary",
	"Balance Sheet",
	"Cash Flow",
	"General Ledger",
	"Gross Profit",
	"Profit and Loss Statement",
	"Purchase Register",
	"Sales Register",
	"Trial Balance",
}
MAX_ROWS = 60
SKIP_FIELDS = {"owner", "modified_by", "creation", "modified", "idx", "doctype", "parent", "parentfield", "parenttype", "_user_tags", "_comments", "_assign", "_liked_by", "_seen"}


def call(name, args):
	"""Run one tool. Errors go back to Barb as text so she can correct herself."""
	tool = TOOLS.get(name)
	if not tool:
		return {"error": f"No tool called {name}"}
	try:
		return tool(**(args or {}))
	except frappe.PermissionError:
		frappe.clear_last_message()
		return {"error": "You don't have permission for that. Tell the user which permission is missing."}
	except Exception as e:
		frappe.clear_last_message()
		return {"error": f"{type(e).__name__}: {str(e)[:400]}"}


def context(doctype=None, name=None):
	"""Who is asking, which companies they can see, and the document open on their screen."""
	companies = frappe.get_list("Company", fields=["name", "abbr", "default_currency", "country"], limit=20)
	default = frappe.defaults.get_user_default("Company") or (companies[0].name if len(companies) == 1 else None)
	fiscal_year = frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": ("<=", today()), "year_end_date": (">=", today())},
		fields=["name", "year_start_date", "year_end_date"],
		limit=1,
	)
	out = {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(),
		"today": today(),
		"companies": companies,
		"default_company": default,
		"fiscal_year": fiscal_year[0] if fiscal_year else None,
	}
	if doctype and name and doctype in DOCTYPES and frappe.has_permission(doctype, "read", name):
		out["open_document"] = get_document(doctype, name)
	return out


def list_documents(doctype, filters=None, fields=None, order_by=None, limit=20):
	_allowed(doctype)
	limit = max(1, min(int(limit or 20), 50))
	return {
		"doctype": doctype,
		"rows": frappe.get_list(
			doctype,
			filters=filters or {},
			fields=fields or ["name"],
			order_by=order_by or "creation desc",
			limit_page_length=limit,
		),
	}


def count_documents(doctype, filters=None):
	_allowed(doctype)
	return {"doctype": doctype, "count": frappe.client.get_count(doctype, filters=filters or {})}


def get_document(doctype, name):
	_allowed(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return _clean(doc.as_dict(no_default_fields=False, convert_dates_to_str=True))


def run_report(report, filters=None):
	if report not in REPORTS:
		raise frappe.ValidationError(f"Barb can run these reports: {', '.join(sorted(REPORTS))}")
	data = run_query_report(report, filters=json.dumps(filters or {}), ignore_prepared_report=True)
	columns = [_column(c) for c in data.get("columns") or []]
	rows = []
	for row in data.get("result") or []:
		if isinstance(row, dict):
			rows.append({c["label"]: row.get(c["fieldname"]) for c in columns if row.get(c["fieldname"]) not in (None, "")})
		elif isinstance(row, (list, tuple)):
			rows.append({c["label"]: v for c, v in zip(columns, row) if v not in (None, "")})
	return {
		"report": report,
		"filters": filters,
		"columns": [c["label"] for c in columns],
		"total_rows": len(rows),
		"rows": rows[:MAX_ROWS],
		"truncated": len(rows) > MAX_ROWS,
	}


def vat_return(company, date_from, date_to):
	"""Prepare (or refresh) the draft VAT201 for a period from the books, and report it by SARS field."""
	filters = {"company": company, "date_from": getdate(date_from), "date_to": getdate(date_to), "docstatus": ("<", 2)}
	existing = frappe.get_list("Value-added Tax Return", filters=filters, fields=["name", "docstatus"], limit=1)
	if existing and existing[0].docstatus == 1:
		doc = frappe.get_doc("Value-added Tax Return", existing[0].name)
		doc.check_permission("read")
		return _vat_summary(doc, "This return is already submitted; these are its figures.")

	created = not existing
	doc = (
		frappe.get_doc("Value-added Tax Return", existing[0].name)
		if existing
		else frappe.get_doc({"doctype": "Value-added Tax Return", "company": company, "date_from": date_from, "date_to": date_to})
	)
	doc.fill_from_books()
	doc.save()
	if created:
		doc.add_comment("Comment", "Prepared by Barb from the books. Check it, classify anything left over, then submit.")
	return _vat_summary(doc, "Draft saved. A person must check and submit it." if created else "Draft refreshed from the books.")


def _vat_summary(doc, note):
	by_field = {}
	for row in doc.gl_entries:
		if row.is_cancelled:
			continue
		by_field.setdefault(row.classification or "Unclassified", []).append(
			{
				"voucher": f"{row.voucher_type} {row.voucher_no}",
				"date": str(row.posting_date),
				"template": row.taxes_and_charges,
				"amount_incl": row.incl_tax_amount,
				"vat": row.tax_amount,
			}
		)
	return {
		"return": doc.name,
		"status": ["Draft", "Submitted", "Cancelled"][doc.docstatus],
		"note": note,
		"company": doc.company,
		"period": f"{doc.date_from} to {doc.date_to}",
		"tax_period": doc.tax_period,
		"vat201": {f: doc.get(fieldname) for f, fieldname in VAT201_FIELDS.items() if doc.get(fieldname)},
		"transactions_by_classification": by_field,
		"unclassified": len(by_field.get("Unclassified", [])),
		"link": f"/desk/value-added-tax-return/{doc.name}",
	}


def _allowed(doctype):
	if doctype not in DOCTYPES:
		raise frappe.ValidationError(f"Barb works with these document types: {', '.join(sorted(DOCTYPES))}")


def _column(c):
	if isinstance(c, dict):
		return {"fieldname": c.get("fieldname") or c.get("label"), "label": c.get("label") or c.get("fieldname")}
	label = str(c).split(":")[0]
	return {"fieldname": frappe.scrub(label), "label": label}


def _clean(value):
	if isinstance(value, dict):
		return {k: _clean(v) for k, v in value.items() if k not in SKIP_FIELDS and v not in (None, "", 0, [])}
	if isinstance(value, list):
		return [_clean(v) for v in value]
	return value


TOOLS = {
	"context": context,
	"list_documents": list_documents,
	"count_documents": count_documents,
	"get_document": get_document,
	"run_report": run_report,
	"vat_return": vat_return,
}
