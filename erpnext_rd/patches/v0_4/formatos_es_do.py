"""Los formatos de impresión de la app pasan al español de República Dominicana (es-DO), salvo que el usuario
les haya puesto otro idioma."""

import frappe

from erpnext_rd.formatos import IDIOMA

MODULOS = ("ERPNext RD", "DGII Fiscal", "ECF", "DGII Reportes", "Padron RNC", "Nomina RD", "RD Compliance")


def execute():
	for nombre in frappe.get_all(
		"Print Format", filters={"module": ("in", MODULOS), "default_print_language": "es"}, pluck="name"
	):
		frappe.db.set_value("Print Format", nombre, "default_print_language", IDIOMA, update_modified=False)
