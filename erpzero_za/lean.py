"""Keep a books site light on a metered Frappe Cloud plan without taking anything away from the user.

Two things, both applied on install:

1. Stop scheduled jobs that belong to features a bookkeeping site never uses (CRM campaigns,
   manufacturing, helpdesk, US bank feeds...). Each one wakes up on a timer and spends the
   site's daily CPU allowance whether or not there is any data. Everything a bookkeeper or
   owner touches stays on: search, email, notifications, reminders, recurring invoices,
   projects, assets, stock, and Builder's page analytics.
2. Turn on Frappe's own log clean-up. Until Log Settings is saved once it holds no entries,
   so error, job and email logs are never cleared and the database grows towards the plan's
   storage cap.

Migrations keep a job's "stopped" flag, so this holds across upgrades. `restore()` switches
the jobs back on when a client grows into one of those modules.
"""

import frappe

STOPPED_JOBS = (
	# CRM: leads, opportunities, campaigns, appointments, contracts
	"erpnext.crm.doctype.appointment.appointment.handle_expired_unverified_appointments",
	"erpnext.crm.doctype.contract.contract.update_status_for_contracts",
	"erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts",
	"erpnext.crm.doctype.email_campaign.email_campaign.set_email_campaign_status",
	"erpnext.crm.doctype.opportunity.opportunity.auto_close_opportunity",
	"erpnext.crm.utils.open_leads_opportunities_based_on_todays_event",
	# Plaid bank feeds: US, Canada and Europe only
	"erpnext.erpnext_integrations.doctype.plaid_settings.plaid_settings.automatic_synchronization",
	# Manufacturing: BOM costing
	"erpnext.manufacturing.doctype.bom_update_log.bom_update_log.resume_bom_cost_update_jobs",
	"erpnext.manufacturing.doctype.bom_update_tool.bom_update_tool.auto_update_latest_price_in_all_boms",
	# Quality, helpdesk, supplier scorecards, YouTube video stats
	"erpnext.quality_management.doctype.quality_review.quality_review.review",
	"erpnext.support.doctype.issue.issue.auto_close_tickets",
	"erpnext.support.doctype.service_level_agreement.service_level_agreement.check_agreement_status",
	"erpnext.buying.doctype.supplier_scorecard.supplier_scorecard.refresh_scorecards",
	"erpnext.utilities.doctype.video.video.update_youtube_data",
	# Google Calendar sync runs every few minutes even with no calendar connected
	"frappe.integrations.doctype.google_calendar.google_calendar.sync",
)


def after_install():
	apply()


def apply():
	_set_stopped(1)
	# Saving runs Log Settings.validate, which adds Frappe's default retention for every log type.
	frappe.get_single("Log Settings").save(ignore_permissions=True)


@frappe.whitelist()
def restore():
	frappe.only_for("System Manager")
	_set_stopped(0)


def _set_stopped(value):
	for name in frappe.get_all("Scheduled Job Type", filters={"method": ("in", STOPPED_JOBS)}, pluck="name"):
		frappe.db.set_value("Scheduled Job Type", name, "stopped", value)
