from erpzero_za import lean


def execute():
	# Sites that installed the app before the lean profile existed (after_install only runs once).
	lean.apply()
