import frappe
from frappe.tests import IntegrationTestCase

from erpzero_za import lean


class TestLean(IntegrationTestCase):
	def test_unused_jobs_stopped_on_install(self):
		jobs = frappe.get_all(
			"Scheduled Job Type", filters={"method": ("in", lean.STOPPED_JOBS)}, fields=["method", "stopped"]
		)
		self.assertTrue(jobs)
		self.assertEqual([j.method for j in jobs if not j.stopped], [])

	def test_books_jobs_left_running(self):
		for method in (
			"frappe.automation.doctype.auto_repeat.auto_repeat.make_auto_repeat_entry",
			"erpnext.assets.doctype.asset.depreciation.post_depreciation_entries",
			"frappe.utils.global_search.sync_global_search",
		):
			self.assertEqual(frappe.db.get_value("Scheduled Job Type", {"method": method}, "stopped"), 0, method)

	def test_log_clean_up_configured(self):
		logs = {r.ref_doctype for r in frappe.get_single("Log Settings").logs_to_clear}
		self.assertIn("Error Log", logs)
		self.assertIn("Scheduled Job Log", logs)
