"""Barb the Bookkeeper moved out of ErpZeroZA into her own app ("barb", from 2nth.ai). Remove the
copies of her doctypes that ErpZeroZA used to install, so the barb app can install its own."""

import frappe


def execute():
	if frappe.db.get_value("Module Def", "Barb", "app_name") != "erpzero_za":
		return  # never had them, or they already belong to the barb app
	for doctype in ("Barb Log", "Barb Settings"):
		if frappe.db.get_value("DocType", doctype, "module") == "Barb":
			frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
	frappe.db.delete("Singles", {"doctype": "Barb Settings"})
	frappe.delete_doc("Module Def", "Barb", force=True, ignore_missing=True)
