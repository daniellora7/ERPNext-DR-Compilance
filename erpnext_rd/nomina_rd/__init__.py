import frappe


def hrms_instalado() -> bool:
	"""Nómina RD solo se activa si Frappe HR (hrms) está instalado en el sitio."""
	return "hrms" in frappe.get_installed_apps()
