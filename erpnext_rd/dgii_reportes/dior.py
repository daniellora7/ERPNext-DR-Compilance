"""Operaciones con partes relacionadas (Fase 8.3): apoyo para la DIOR.

Base (página de Precios de Transferencia de la DGII, leída el 2026-11-11): presentan la Declaración
Informativa de Operaciones con Relacionados (DIOR) los contribuyentes que operan con partes
relacionadas residentes o del exterior, o con jurisdicciones de baja o nula tributación (Código
Tributario arts. 281 a 281 quáter, Reglamento 78-14). Se presenta cada año en la Oficina Virtual, a
más tardar 180 días después del cierre del ejercicio.

La app reúne las ventas y compras del ejercicio con los clientes y proveedores marcados como parte
relacionada, por contraparte. El instructivo con los campos de cada operación no estaba disponible
(404); los métodos de precios de transferencia y el estudio de valoración se hacen fuera de la app.
"""

from datetime import date

import frappe
from frappe.utils import add_days, flt, getdate

DIAS_PRESENTACION = 180
VENTA = "Venta"
COMPRA = "Compra"


def fecha_limite(cierre) -> date:
	"""Último día para presentar la DIOR del ejercicio cerrado en `cierre` (sin correr a día hábil)."""
	return add_days(getdate(cierre), DIAS_PRESENTACION)


def relacionados() -> dict[str, list[str]]:
	return {
		"Customer": frappe.get_all("Customer", filters={"rd_parte_relacionada": 1}, pluck="name"),
		"Supplier": frappe.get_all("Supplier", filters={"rd_parte_relacionada": 1}, pluck="name"),
	}


def operaciones(company: str, desde, hasta) -> list[frappe._dict]:
	"""Ventas y compras aprobadas del período con partes relacionadas, por contraparte y tipo.

	Montos netos de ITBIS en la moneda de la empresa; las notas de crédito restan."""
	partes = relacionados()
	filas = []
	for doctype, parte, campo_parte, tipo in (
		("Sales Invoice", "Customer", "customer", VENTA),
		("Purchase Invoice", "Supplier", "supplier", COMPRA),
	):
		if not partes[parte]:
			continue
		for f in frappe.get_all(
			doctype,
			filters={
				"company": company,
				"docstatus": 1,
				campo_parte: ("in", partes[parte]),
				"posting_date": ("between", (getdate(desde), getdate(hasta))),
			},
			fields=[
				campo_parte,
				{"SUM": "base_net_total", "as": "monto"},
				{"COUNT": "name", "as": "documentos"},
			],
			group_by=campo_parte,
		):
			datos = frappe.db.get_value(
				parte,
				f[campo_parte],
				["tax_id", "rd_vinculacion", f"{'customer' if parte == 'Customer' else 'supplier'}_name"]
				+ (["country"] if parte == "Supplier" else []),
				as_dict=True,
			)
			filas.append(
				frappe._dict(
					tipo=tipo,
					parte=parte,
					contraparte=f[campo_parte],
					nombre=datos.get("customer_name") or datos.get("supplier_name"),
					identificacion=datos.tax_id,
					pais=datos.get("country"),
					vinculacion=datos.rd_vinculacion,
					documentos=f.documentos,
					monto=flt(f.monto),
				)
			)
	return sorted(filas, key=lambda f: (f.nombre or "", f.tipo))
