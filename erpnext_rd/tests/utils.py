"""Preparación del sitio para los tests."""

import frappe
from frappe.utils import now_datetime


def antes_de_tests():
	"""before_tests: en un sitio recién creado (CI) completa el asistente de configuración como
	empresa de República Dominicana, para que existan los registros base (bodegas, UOM, géneros,
	modos de pago...). En un sitio que ya tiene empresas no hace nada."""
	if frappe.get_all("Company", limit=1):
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	anio = now_datetime().year
	setup_complete(
		{
			"currency": "DOP",
			"full_name": "Usuario de Pruebas",
			"company_name": "_Test Empresa CI",
			"timezone": "America/Santo_Domingo",
			"company_abbr": "_TCI",
			"industry": "Manufacturing",
			"country": "Dominican Republic",
			"fy_start_date": f"{anio}-01-01",
			"fy_end_date": f"{anio}-12-31",
			"language": "english",
			"company_tagline": "Pruebas",
			"email": "pruebas@erpnext-rd.test",
			"password": frappe.generate_hash(length=24),
			"chart_of_accounts": "Standard",
		}
	)
	frappe.db.commit()  # nosemgrep
