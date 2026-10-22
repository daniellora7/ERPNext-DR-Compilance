"""Módulos de la app solo para quienes trabajan con empresas de RD. El idioma es-DO ya se aplicó en los
sitios que existían: se marca como hecho para que no se vuelva a aplicar al crear una empresa."""

import frappe

from erpnext_rd.rd_compliance import alcance


def execute():
	alcance.sincronizar_todos()
	if frappe.get_all("Company", limit=1):
		frappe.db.set_default(alcance.CLAVE_IDIOMA, "1")
