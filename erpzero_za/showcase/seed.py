"""A year of trading for a demo company: the daily work a bookkeeper on Xero would recognise.

Never runs on install. Builds the business (customers, suppliers, items, accounts, bank, payment
terms) and then trades day by day: quotes become invoices, customers pay on their own habits (on time,
late, in part, or not at all), suppliers are paid in a Friday run, kettles come back on credit notes,
salaries and the EMP201 go through each month, and each two-monthly VAT period (Category B) is
prepared from the books, submitted and paid to SARS.

Every number comes from a random generator seeded by the company and the date, so a run is
repeatable, and every document carries a reference (KK-...) so re-running a day creates nothing twice.

A "teaching window" (by default 1 Sep to 31 Oct 2026, the seven-invoice VAT201 example) is kept clean
of anything that touches VAT; payments and salaries still go through in it.

	erpzero_za.showcase.seed.start("Karoo Kettle Co")      # whitelisted; queues the run
"""

import random
from datetime import date, timedelta

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe.utils import add_days, add_months, flt, get_last_day, getdate, today

from erpzero_za.za_books import vat

START = date(2026, 3, 1)
TEACHING = (date(2026, 9, 1), date(2026, 10, 31))
PUBLIC_HOLIDAYS = {
	date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 27), date(2026, 5, 1), date(2026, 6, 16),
	date(2026, 8, 10), date(2026, 9, 24), date(2026, 12, 16), date(2026, 12, 25),
	date(2027, 1, 1), date(2027, 3, 22),
}  # Public Holidays Act 36 of 1994, with Sunday holidays moved to the Monday

# ---------- the business ----------

TERMS = {"COD": 0, "7 days": 7, "30 days": 30}

ITEMS = {
	# code: (name, rate, kind)  kind: sale | buy:<expense account> | rent
	"KK-ENAMEL-15": ("Enamel kettle 1.5 L, Karoo red", 450, "sale"),
	"KK-ENAMEL-10": ("Enamel kettle 1.0 L, veld green", 395, "sale"),
	"KK-STOVETOP-20": ("Stovetop kettle 2.0 L, white", 520, "sale"),
	"KK-CAMP-08": ("Camp kettle 0.8 L, black", 320, "sale"),
	"KK-MUG-SET4": ("Enamel mug set of 4", 260, "sale"),
	"KK-LID-SPARE": ("Spare kettle lid", 85, "sale"),
	"KK-COTTAGE-RENT": ("Cottage rent, residential", 4500, "rent"),
	"KK-STEEL-SHEET": ("Mild steel sheet 1.2 mm", 600, "buy:Cost of Goods Sold"),
	"KK-FRIT": ("Enamel frit, 25 kg bag", 1850, "buy:Cost of Goods Sold"),
	"KK-CARTONS": ("Kettle cartons, bundle of 50", 690, "buy:Cost of Goods Sold"),
	"KK-COURIER": ("Courier, weekly collections", 1250, "buy:Freight and Forwarding Charges"),
	"KK-POWER": ("Electricity and water", 3800, "buy:Utility Expenses"),
	"KK-INSURE": ("Business insurance premium", 1450, "buy:Insurance"),
	"KK-BANKFEES": ("Bank fees", 420, "buy:Bank Charges"),
	"KK-REPAIRS": ("Workshop repairs and maintenance", 1800, "buy:Office Maintenance Expenses"),
}

# name: (terms, habit, VAT number, address line, town, postcode, country, buys)
#   habit: cod | prompt | late | part | stops (stops paying from July: a debtor to chase)
CUSTOMERS = {
	"Walk-in Customers": ("COD", "cod", None, None, None, None, "South Africa", "few"),
	"Nieu-Bethesda Farm Stall": ("7 days", "prompt", None, "Martin Street", "Nieu-Bethesda", "6286", "South Africa", "small"),
	"Karoo Padstal (Pty) Ltd": ("30 days", "prompt", "4910000117", "N9 Road", "Graaff-Reinet", "6280", "South Africa", "medium"),
	"Signal Hill Provisions": ("30 days", "late", "4910000125", "Kloof Street", "Cape Town", "8001", "South Africa", "medium"),
	"Rosebank Kitchen Corner": ("30 days", "part", "4910000133", "Tyrwhitt Avenue", "Johannesburg", "2196", "South Africa", "medium"),
	"Home & Hearth Stores (Pty) Ltd": ("30 days", "prompt", "4910000141", "Commissioner Street", "Johannesburg", "2001", "South Africa", "large"),
	"Camdeboo Lodge": ("30 days", "stops", "4910000158", "Valley Road", "Graaff-Reinet", "6280", "South Africa", "small"),
	"Willowmore Farm Supplies": ("30 days", "late", None, "Wehmeyer Street", "Willowmore", "6445", "South Africa", "small"),
	"Gaborone Homeware (Botswana)": ("30 days", "prompt", None, "Plot 1234, Broadhurst", "Gaborone", None, "Botswana", "export"),
	"T. Mokoena (cottage tenant)": ("7 days", "prompt", None, "The Cottage, Main Road", "Nieu-Bethesda", "6286", "South Africa", "rent"),
}

# name: (terms, VAT number, items it bills, when, VAT template title)
#   when: "1st", "15th", "monthly:5", "weekly:Mon", "monthly:last", "every:45"
SUPPLIERS = {
	"Gqeberha Steel Supply": ("30 days", "4920000114", ("KK-STEEL-SHEET",), "twice-monthly", "Standard rate 15%"),
	"Frit & Glaze SA (Pty) Ltd": ("30 days", "4920000122", ("KK-FRIT",), "monthly:5", "Standard rate 15%"),
	"Karoo Box & Carton": ("30 days", "4920000130", ("KK-CARTONS",), "monthly:10", "Standard rate 15%"),
	"Swift Couriers SA": ("7 days", "4920000148", ("KK-COURIER",), "weekly:0", "Standard rate 15%"),
	"Camdeboo Municipal Services": ("COD", "4920000155", ("KK-POWER",), "monthly:3", "Standard rate 15%"),
	"Shield Insurance Brokers": ("COD", "4920000163", ("KK-INSURE",), "monthly:1", "Standard rate 15%"),
	"FNB": ("COD", "4920000171", ("KK-BANKFEES",), "monthly:last", "Standard rate 15%"),
	"Piet's Handyman Services": ("COD", None, ("KK-REPAIRS",), "every:45", "No VAT"),
}

PAYROLL = {"gross": 98000, "paye": 14200, "uif_each": 980, "sdl": 980}
OPENING = {"bank": 250000, "Capital Equipment": 180000}
CREDIT_REASONS = (
	"Kettle returned with chipped enamel",
	"Lid did not fit: kettle returned",
	"Damaged in transit, confirmed with the courier",
	"Wrong colour sent: returned unused",
)


# ---------- entry points ----------


@frappe.whitelist()
def start(company, from_date=None, to_date=None):
	"""Queue a run (System Manager). Safe to repeat: days already traded are skipped."""
	frappe.only_for("System Manager")
	frappe.enqueue("erpzero_za.showcase.seed.run", queue="long", timeout=4 * 3600, company=company, from_date=from_date, to_date=to_date)
	return "Queued: the year is being built in the background."


def run(company, from_date=None, to_date=None):
	set_up(company)
	frappe.db.commit()
	day = getdate(from_date or START)
	end = getdate(to_date or today())
	while day <= end:
		trade_day(company, day)
		frappe.db.commit()
		day += timedelta(days=1)


def living_demo():
	"""Daily: the showcase company trades today, so the demo always has today's work in it."""
	s = frappe.get_cached_doc("Showcase Settings")
	if s.enabled and s.get("living_demo") and s.company and frappe.db.exists("Customer", "Walk-in Customers"):
		trade_day(s.company, getdate(today()))
		frappe.db.commit()


# ---------- setting up the business ----------


def set_up(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	bank = _ensure_account(company, "FNB Business Cheque", "Bank Accounts", "Bank")
	vat_parent = frappe.db.get_value("Account", vat.get_vat_account(company), "parent_account")
	for name in ("PAYE Payable", "UIF Payable", "SDL Payable"):
		_ensure_account(company, name, vat_parent)
	_ensure_account(company, "Insurance", frappe.db.get_value("Account", f"Administrative Expenses - {abbr}", "parent_account"))
	_ensure_account(company, "Rental Income", frappe.db.get_value("Account", f"Interest Income - {abbr}", "parent_account"))
	frappe.db.set_value("Company", company, "default_bank_account", bank)
	if not frappe.db.get_value("Company", company, "tax_id"):
		frappe.db.set_value("Company", company, "tax_id", "4999999990")  # fictitious
	_address("Company", company, "Main Road", "Nieu-Bethesda", "6286", "South Africa", company_address=True)
	_bank_account(company, bank)

	for name, days in TERMS.items():
		if not frappe.db.exists("Payment Terms Template", name):
			frappe.get_doc({"doctype": "Payment Terms Template", "template_name": name,
				"terms": [{"invoice_portion": 100, "due_date_based_on": "Day(s) after invoice date", "credit_days": days}]}).insert()

	for code, (name, rate, kind) in ITEMS.items():
		if frappe.db.exists("Item", code):
			continue
		item = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "description": name, "stock_uom": "Nos",
			"is_stock_item": 0, "item_group": "Services" if kind != "sale" else "Products",
			"is_sales_item": int(kind in ("sale", "rent")), "is_purchase_item": int(kind.startswith("buy")), "standard_rate": rate})
		if kind == "rent":
			item.append("item_defaults", {"company": company, "income_account": f"Rental Income - {abbr}"})
		elif kind.startswith("buy:"):
			item.append("item_defaults", {"company": company, "expense_account": f"{kind[4:]} - {abbr}"})
		item.insert()

	for name, (terms, habit, vat_no, line, town, code, country, _buys) in CUSTOMERS.items():
		if not frappe.db.exists("Customer", name):
			frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company",
				"customer_group": "Individual" if habit == "cod" else "Commercial",
				"territory": "South Africa" if country == "South Africa" else "Rest Of The World",
				"payment_terms": terms, "tax_id": vat_no}).insert()
		if line:
			_address("Customer", name, line, town, code, country)

	for name, (terms, vat_no, _items, _when, _tpl) in SUPPLIERS.items():
		if not frappe.db.exists("Supplier", name):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": "Local",
				"payment_terms": terms, "tax_id": vat_no}).insert()

	if not _exists("Journal Entry", company, "cheque_no", "KK-OPENING"):
		_journal(company, START, "KK-OPENING", "Opening balances at 1 March 2026", [
			(bank, OPENING["bank"], 0), (f"Capital Equipment - {abbr}", OPENING["Capital Equipment"], 0),
			(f"Capital Stock - {abbr}", 0, sum(OPENING.values())),
		], opening=True)


# ---------- one trading day ----------


def trade_day(company, day):
	rng = random.Random(f"{company}|{day.isoformat()}")
	teaching = TEACHING[0] <= day <= TEACHING[1]
	working = day.weekday() < 5 and day not in PUBLIC_HOLIDAYS

	if not teaching:
		if working:
			_sales(company, day, rng)
			_purchases(company, day, rng)
			if _first_working_day_from(day, 2) or _first_working_day_from(day, 16):
				_credit_note(company, day, rng)
		if day.day == 1:
			_sell(company, day, "T. Mokoena (cottage tenant)", [("KK-COTTAGE-RENT", 1)], "Exempt", "RENT")
		if day == get_last_day(day):
			_buy(company, _last_working_day(day), "FNB", 1, rng, ref_day=day)
		_vat_period(company, day)

	if working:
		_customer_payments(company, day)
		if day.weekday() == 4:
			_supplier_run(company, day)
	_payroll(company, day)


def _sales(company, day, rng):
	weights = {"few": 0.5, "small": 0.25, "medium": 0.35, "large": 0.2, "export": 0.05, "rent": 0}
	n = 0
	for customer, (*_rest, buys) in CUSTOMERS.items():
		if rng.random() >= weights[buys]:
			continue
		n += 1
		sale_items = [c for c, (_n, _r, k) in ITEMS.items() if k == "sale"]
		lines = []
		for code in rng.sample(sale_items, rng.randint(1, 3)):
			qty = {"few": rng.randint(1, 2), "small": rng.randint(2, 8), "medium": rng.randint(6, 24),
				"large": rng.randint(24, 72), "export": rng.randint(40, 120)}[buys]
			lines.append((code, qty))
		_sell(company, day, customer, lines, "Exports 0%" if buys == "export" else "Standard rate 15%", f"S{n}")


def _sell(company, day, customer, lines, template, tag):
	if customer not in CUSTOMERS and not frappe.db.exists("Customer", customer):
		return None
	ref = f"KK-{day:%Y%m%d}-{tag}"
	if _exists("Sales Invoice", company, "po_no", ref):
		return None
	doc = frappe.get_doc({"doctype": "Sales Invoice", "company": company, "customer": customer, "posting_date": day,
		"set_posting_time": 1, "po_no": ref, "items": [{"item_code": c, "qty": q, "rate": ITEMS[c][1]} for c, q in lines]})
	_taxes(doc, company, vat.SALES, template)
	doc.insert()
	doc.submit()
	if CUSTOMERS.get(customer, ("",))[0] == "COD":
		_receive(company, doc.name, day, doc.grand_total)
	return doc


def _purchases(company, day, rng):
	for supplier, (_terms, _vat, items, when, _tpl) in SUPPLIERS.items():
		if supplier == "FNB":
			continue
		kind, _, arg = when.partition(":")
		due = (
			(kind == "twice-monthly" and (_first_working_day_from(day, 1) or _first_working_day_from(day, 15)))
			or (kind == "monthly" and _first_working_day_from(day, int(arg)))
			or (kind == "weekly" and day.weekday() == int(arg))
			or (kind == "every" and (day - START).days % int(arg) < 3 and not _exists_recent(company, supplier, day, int(arg)))
		)
		if due:
			_buy(company, day, supplier, rng.randint(4, 12) if items[0] == "KK-STEEL-SHEET" else 1, rng)


def _buy(company, day, supplier, qty, rng, ref_day=None):
	terms, _vat, items, _when, template = SUPPLIERS[supplier]
	ref = f"KK-{(ref_day or day):%Y%m%d}-{supplier[:3].upper()}"
	if _exists("Purchase Invoice", company, "bill_no", ref):
		return
	rate = ITEMS[items[0]][1] * (1 + rng.uniform(-0.08, 0.08))
	doc = frappe.get_doc({"doctype": "Purchase Invoice", "company": company, "supplier": supplier, "posting_date": day,
		"set_posting_time": 1, "bill_no": ref, "bill_date": day, "items": [{"item_code": items[0], "qty": qty, "rate": round(rate, 2)}]})
	_taxes(doc, company, vat.PURCHASE, template)
	doc.insert()
	doc.submit()
	if terms == "COD":  # debit orders and card payments go off the same day
		_pay_supplier(company, doc.name, day)


def _credit_note(company, day, rng):
	ref = f"KK-{day:%Y%m%d}-CN"
	if _exists("Sales Invoice", company, "po_no", ref):
		return
	candidates = frappe.get_all("Sales Invoice", filters={"company": company, "docstatus": 1, "is_return": 0, "outstanding_amount": (">", 0),
		"posting_date": ("between", (add_days(day, -30), add_days(day, -1))), "taxes_and_charges": ("like", "Standard rate%"),
		"customer": ("not in", ("Walk-in Customers",))}, pluck="name", order_by="name")
	if not candidates:
		return
	original = rng.choice(candidates)
	ret = make_sales_return(original)
	ret.items = ret.items[:1]
	ret.items[0].qty = -1
	ret.posting_date, ret.set_posting_time, ret.po_no = day, 1, ref
	ret.remarks = rng.choice(CREDIT_REASONS)
	if ret.meta.has_field("update_outstanding_for_self"):
		ret.update_outstanding_for_self = 0  # reduce what the customer owes on the original invoice
	ret.insert()
	ret.submit()


def _customer_payments(company, day):
	for inv in frappe.get_all("Sales Invoice", filters={"company": company, "docstatus": 1, "is_return": 0,
			"outstanding_amount": (">", 0), "posting_date": ("<", day)},
			fields=["name", "customer", "due_date", "grand_total", "outstanding_amount"]):
		habit = CUSTOMERS.get(inv.customer, ("", "prompt"))[1]
		jitter = random.Random(inv.name).randint(-3, 4)
		pay_on = add_days(inv.due_date, jitter + {"prompt": 0, "late": 24, "part": 2, "stops": 0, "cod": 0}.get(habit, 0))
		if habit == "stops" and getdate(inv.due_date) >= date(2026, 7, 1):
			continue  # stopped paying: shows up in the debtors' age analysis
		if getdate(pay_on) > day:
			continue
		amount = inv.outstanding_amount
		if habit == "part" and flt(inv.outstanding_amount) >= flt(inv.grand_total) - 1:
			amount = round(inv.outstanding_amount / 2, 2)  # half now ...
		elif habit == "part" and getdate(add_days(pay_on, 14)) > day:
			continue  # ... the rest two weeks later
		_receive(company, inv.name, day, amount)


def _supplier_run(company, day):
	for name in frappe.get_all("Purchase Invoice", filters={"company": company, "docstatus": 1, "outstanding_amount": (">", 0),
			"due_date": ("<=", add_days(day, 7))}, pluck="name", order_by="due_date"):
		_pay_supplier(company, name, day)


def _payroll(company, day):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	bank = frappe.get_cached_value("Company", company, "default_bank_account")
	p = PAYROLL
	if day == _last_working_day_on_or_before(date(day.year, day.month, 25)):
		ref = f"KK-{day:%Y%m}-PAY"
		if not _exists("Journal Entry", company, "cheque_no", ref):
			net = p["gross"] - p["paye"] - p["uif_each"]
			_journal(company, day, ref, f"Salaries for {day:%B %Y}: gross {p['gross']}, PAYE, UIF and SDL from the payroll report", [
				(f"Salary - {abbr}", p["gross"] + p["uif_each"] + p["sdl"], 0),
				(f"PAYE Payable - {abbr}", 0, p["paye"]), (f"UIF Payable - {abbr}", 0, 2 * p["uif_each"]),
				(f"SDL Payable - {abbr}", 0, p["sdl"]), (bank, 0, net)])
	if day.day == 7 and day > START:
		ref = f"KK-{day:%Y%m}-EMP201"
		if not _exists("Journal Entry", company, "cheque_no", ref):
			_journal(company, day, ref, f"EMP201 for {add_months(day, -1):%B %Y} paid to SARS", [
				(f"PAYE Payable - {abbr}", p["paye"], 0), (f"UIF Payable - {abbr}", 2 * p["uif_each"], 0),
				(f"SDL Payable - {abbr}", p["sdl"], 0), (bank, 0, p["paye"] + 2 * p["uif_each"] + p["sdl"])])


def _vat_period(company, day):
	"""Category B: two-monthly periods ending in even months. Submit at period end; pay on the 25th."""
	if day.month % 2 == 0 and day == get_last_day(day):
		period_start = date(day.year, day.month - 1, 1)
		if not (TEACHING[0] <= period_start <= TEACHING[1]):
			ret = _vat_return(company, period_start, day)
			if ret and ret.docstatus == 0:
				frappe.db.commit()  # keep the day's work if the submit below has to be rolled back
				try:
					ret.submit()
				except frappe.ValidationError:
					frappe.db.rollback()  # e.g. something unclassified: left as a draft for a person, as in real life
					frappe.log_error(title=f"Demo VAT return {period_start}–{day} left as a draft")
	if day.day == 25 and day.month % 2 == 1:
		end = get_last_day(add_months(day, -1))
		name = frappe.db.get_value("Value-added Tax Return", {"company": company, "date_to": end, "docstatus": 1},
			["name", "total_vat_payable_refundable"], as_dict=True)
		ref = f"KK-{end:%Y%m}-VAT"
		if name and not _exists("Journal Entry", company, "cheque_no", ref):
			amount = flt(name.total_vat_payable_refundable)
			bank, vat_account = frappe.get_cached_value("Company", company, "default_bank_account"), vat.get_vat_account(company)
			rows = [(vat_account, amount, 0), (bank, 0, amount)] if amount > 0 else [(bank, -amount, 0), (vat_account, 0, -amount)]
			_journal(company, day, ref, f"VAT201 {name.name}: {'paid to' if amount > 0 else 'refund from'} SARS", rows)


def _vat_return(company, date_from, date_to):
	existing = frappe.db.get_value("Value-added Tax Return", {"company": company, "date_from": date_from, "date_to": date_to, "docstatus": ("<", 2)})
	doc = frappe.get_doc("Value-added Tax Return", existing) if existing else frappe.get_doc(
		{"doctype": "Value-added Tax Return", "company": company, "date_from": date_from, "date_to": date_to})
	if doc.docstatus == 1:
		return doc
	doc.fill_from_books()
	doc.save()
	return doc


# ---------- helpers ----------


def _receive(company, invoice, day, amount):
	ref = f"KK-{day:%Y%m%d}-R-{invoice}"
	if _exists("Payment Entry", company, "reference_no", ref):
		return
	pe = get_payment_entry("Sales Invoice", invoice, party_amount=amount)
	pe.update({"posting_date": day, "reference_no": ref, "reference_date": day})
	pe.insert()
	pe.submit()


def _pay_supplier(company, invoice, day):
	ref = f"KK-{day:%Y%m%d}-P-{invoice}"
	if _exists("Payment Entry", company, "reference_no", ref):
		return
	pe = get_payment_entry("Purchase Invoice", invoice)
	pe.update({"posting_date": day, "reference_no": ref, "reference_date": day})
	pe.insert()
	pe.submit()


def _journal(company, day, ref, remark, rows, opening=False):
	je = frappe.get_doc({"doctype": "Journal Entry", "company": company, "posting_date": day, "cheque_no": ref, "cheque_date": day,
		"user_remark": remark, "is_opening": "Yes" if opening else "No",
		"accounts": [{"account": a, "debit_in_account_currency": dr, "credit_in_account_currency": cr} for a, dr, cr in rows]})
	je.insert()
	je.submit()
	return je


def _taxes(doc, company, master, title):
	template = f"{title} - {frappe.get_cached_value('Company', company, 'abbr')}"
	doc.taxes_and_charges = template
	doc.set("taxes", get_taxes_and_charges(master, template))


def _exists(doctype, company, field, value):
	return frappe.db.exists(doctype, {"company": company, field: value, "docstatus": ("<", 2)})


def _ensure_account(company, name, parent, account_type=None):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	if not parent.endswith(f" - {abbr}"):
		parent = frappe.db.get_value("Account", {"company": company, "account_name": parent, "is_group": 1}) or frappe.db.get_value(
			"Account", frappe.get_cached_value("Company", company, "default_cash_account"), "parent_account")
	full = f"{name} - {abbr}"
	if not frappe.db.exists("Account", full):
		frappe.get_doc({"doctype": "Account", "account_name": name, "company": company, "parent_account": parent,
			"account_type": account_type}).insert()
	return full


def _address(link_doctype, link_name, line, town, code, country, company_address=False):
	if frappe.db.exists("Dynamic Link", {"link_doctype": link_doctype, "link_name": link_name, "parenttype": "Address"}):
		return
	frappe.get_doc({"doctype": "Address", "address_title": link_name, "address_type": "Billing", "address_line1": line,
		"city": town, "pincode": code, "country": country, "is_primary_address": 1, "is_your_company_address": int(company_address),
		"links": [{"link_doctype": link_doctype, "link_name": link_name}]}).insert()


def _bank_account(company, gl_account):
	if not frappe.db.exists("Bank", "FNB"):
		frappe.get_doc({"doctype": "Bank", "bank_name": "FNB"}).insert()
	if not frappe.db.exists("Bank Account", {"company": company, "account": gl_account}):
		frappe.get_doc({"doctype": "Bank Account", "account_name": "Business Cheque", "bank": "FNB", "company": company,
			"account": gl_account, "is_company_account": 1, "is_default": 1, "bank_account_no": "62000000000",
			"branch_code": "250655"}).insert()


def _first_working_day_from(day, n):
	"""True on the first working day on or after the nth of the month."""
	if day.weekday() >= 5 or day in PUBLIC_HOLIDAYS or day.day < n:
		return False
	d = date(day.year, day.month, n)
	while d < day:
		if d.weekday() < 5 and d not in PUBLIC_HOLIDAYS:
			return False
		d += timedelta(days=1)
	return True


def _exists_recent(company, supplier, day, days):
	return frappe.db.exists("Purchase Invoice", {"company": company, "supplier": supplier, "docstatus": 1,
		"posting_date": ("between", (add_days(day, -days + 5), day))})


def _last_working_day(day):
	day = get_last_day(day)
	while day.weekday() >= 5 or day in PUBLIC_HOLIDAYS:
		day -= timedelta(days=1)
	return day


def _last_working_day_on_or_before(day):
	while day.weekday() >= 5 or day in PUBLIC_HOLIDAYS:
		day -= timedelta(days=1)
	return day
