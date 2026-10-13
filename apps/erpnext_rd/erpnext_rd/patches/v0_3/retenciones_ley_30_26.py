"""Ley 30-26: la retención de ISR a personas físicas (art. 309) pasa de 10% a 15% desde el 1/7/2026.

Actualiza las plantillas de compra que creó la app con la tasa vieja (solo si el usuario no les
cambió la tasa) y agrega la plantilla de servicios técnicos (3% efectivo) a las empresas con el
catálogo DGII.
"""

import frappe

from erpnext_rd.dgii_fiscal import catalogo_cuentas as cc

DOCTYPE = "Purchase Taxes and Charges Template"


def execute():
	for viejo, nuevo in cc.PLANTILLAS_RENOMBRADAS.items():
		for nombre in frappe.get_all(DOCTYPE, filters={"title": viejo}, pluck="name"):
			doc = frappe.get_doc(DOCTYPE, nombre)
			filas_isr = [
				f
				for f in doc.taxes
				if f.rate == 10 and f.add_deduct_tax == "Deduct" and "ISR" in (f.description or "")
			]
			if not filas_isr or frappe.db.exists(DOCTYPE, {"title": nuevo, "company": doc.company}):
				continue
			for fila in filas_isr:
				fila.rate = 15
				fila.description = "Retención ISR 15%"
			doc.title = nuevo
			doc.save(ignore_permissions=True)
			nombre_nuevo = f"{nuevo} - {frappe.get_cached_value('Company', doc.company, 'abbr')}"
			if nombre_nuevo != doc.name and not frappe.db.exists(DOCTYPE, nombre_nuevo):
				frappe.rename_doc(DOCTYPE, doc.name, nombre_nuevo, force=True)

	for company in frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name"):
		cc._crear_plantillas_impuestos(company, cc._cuentas_por_numero(company))
