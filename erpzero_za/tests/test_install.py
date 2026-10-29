import frappe
from frappe.tests import IntegrationTestCase

MODULES = ("ZA Books", "Xero Migration", "Bank", "Payroll Bridge", "Payments")


class TestInstall(IntegrationTestCase):
	def test_modules_registered(self):
		for module in MODULES:
			self.assertEqual(frappe.db.get_value("Module Def", module, "app_name"), "erpzero_za", module)
