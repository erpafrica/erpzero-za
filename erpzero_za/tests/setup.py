import frappe
from erpnext.setup.utils import enable_all_roles_and_domains
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.utils import getdate, today


def before_tests():
	"""A South African company with a March–February year, as most SA small businesses have."""
	frappe.clear_cache()
	if not frappe.db.a_row_exists("Company"):
		now = getdate(today())
		start = now.year if now.month >= 3 else now.year - 1
		setup_complete(
			{
				"currency": "ZAR",
				"full_name": "Test User",
				"company_name": "Test Books ZA",
				"company_abbr": "TBZ",
				"timezone": "Africa/Johannesburg",
				"country": "South Africa",
				"fy_start_date": f"{start}-03-01",
				"fy_end_date": f"{start + 1}-02-{29 if (start + 1) % 4 == 0 else 28}",
				"language": "english",
				"email": "test@example.com",
				"password": "test",
				"chart_of_accounts": "Standard",
			}
		)
	enable_all_roles_and_domains()
	frappe.db.commit()  # nosemgrep
