"""Bloque «Compras recibidas» del Panel RD Compliance (plan de captura de compras, 1.5).

Solo lee: e-CF de proveedores sin factura de compra, facturas en borrador creadas desde un e-CF,
aprobaciones comerciales pendientes y capturas del celular que aún no pasan a factura.
"""

import frappe
from frappe.query_builder.functions import Count

RECIBIDO = "ECF Recibido"
CAPTURA = "Captura Compra"
# Conversión que todavía no tiene factura de compra
SIN_FACTURA = ("Pendiente", "Error")
# Conversión con factura en borrador creada por la app
CON_BORRADOR = ("Borrador creado", "Requiere revisión")
# Capturas que aún no son factura (ni duplicadas ni descartadas)
CAPTURA_ABIERTA = ("Pendiente", "Requiere revisión", "Lista")


def resumen(company: str) -> dict | None:
	"""None si el usuario no ve los e-CF recibidos o la empresa no recibe compras por la app."""
	if not frappe.has_permission(RECIBIDO, "read"):
		return None
	ve_capturas = bool(frappe.has_permission(CAPTURA, "read"))
	if not frappe.db.exists(RECIBIDO, {"company": company}) and not (
		ve_capturas and frappe.db.exists(CAPTURA, {"company": company})
	):
		return None

	base = {"company": company, "estado": "Recibido"}
	return {
		"sin_factura": frappe.db.count(RECIBIDO, {**base, "estado_conversion": ("in", SIN_FACTURA)}),
		"con_error": frappe.db.count(RECIBIDO, {**base, "estado_conversion": "Error"}),
		"en_borrador": en_borrador(company),
		"por_aprobar": frappe.db.count(RECIBIDO, {**base, "aprobacion": "Pendiente"}),
		"capturas": (
			frappe.db.count(CAPTURA, {"company": company, "estado": ("in", CAPTURA_ABIERTA)})
			if ve_capturas
			else None
		),
	}


def en_borrador(company: str) -> int:
	"""e-CF recibidos cuya factura de compra creada por la app sigue en borrador."""
	recibido = frappe.qb.DocType(RECIBIDO)
	factura = frappe.qb.DocType("Purchase Invoice")
	fila = (
		frappe.qb.from_(recibido)
		.join(factura)
		.on(factura.name == recibido.factura_compra)
		.select(Count(recibido.name))
		.where(recibido.company == company)
		.where(recibido.estado_conversion.isin(CON_BORRADOR))
		.where(factura.docstatus == 0)
	).run()
	return fila[0][0] if fila else 0
