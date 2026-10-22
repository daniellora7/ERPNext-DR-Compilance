"""Campo «Perfil tributario» (solo lectura) en la empresa: se llena con los perfiles que ya existen."""

import frappe

from erpnext_rd.install import crear_campos_personalizados
from erpnext_rd.rd_compliance.perfil import resumen


def execute():
	# Los patches corren antes que after_migrate, que es quien crea los campos personalizados
	crear_campos_personalizados()
	for perfil in frappe.get_all(
		"Perfil Tributario RD", fields=["name", "company", "tipo_contribuyente", "tipo_sociedad", "regimen"]
	):
		frappe.db.set_value(
			"Perfil Tributario RD", perfil.name, "resumen", resumen(perfil), update_modified=False
		)
		frappe.db.set_value(
			"Company", perfil.company, "rd_perfil_tributario", perfil.name, update_modified=False
		)
