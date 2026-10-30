from frappe.model.document import Document

from erpzero_za.showcase import guests


class ShowcaseSettings(Document):
	def on_update(self):
		if self.enabled:
			guests.setup()
