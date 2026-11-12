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
from frappe.query_builder.functions import Count, IfNull, Sum
from frappe.utils import add_days, flt, getdate

DIAS_PRESENTACION = 180
VENTA = "Venta"
COMPRA = "Compra"
ASIENTO = "Asiento"


def fecha_limite(cierre) -> date:
	"""Último día para presentar la DIOR del ejercicio cerrado en `cierre` (sin correr a día hábil)."""
	return add_days(getdate(cierre), DIAS_PRESENTACION)


def relacionados() -> dict[str, list[str]]:
	return {
		"Customer": frappe.get_all("Customer", filters={"rd_parte_relacionada": 1}, pluck="name"),
		"Supplier": frappe.get_all("Supplier", filters={"rd_parte_relacionada": 1}, pluck="name"),
	}


def operaciones(company: str, desde, hasta) -> list[frappe._dict]:
	"""Ventas y compras aprobadas del período con partes relacionadas, por contraparte y tipo, y los
	asientos con ellas que no pagan facturas (préstamos, anticipos, cargos entre compañías...).

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
			filas.append(_fila(parte, f[campo_parte], tipo, documentos=f.documentos, monto=flt(f.monto)))
	filas += asientos(company, desde, hasta, partes)
	return sorted(filas, key=lambda f: (f.nombre or "", f.tipo))


def _fila(parte: str, contraparte: str, tipo: str, **montos) -> frappe._dict:
	campo_nombre = "customer_name" if parte == "Customer" else "supplier_name"
	datos = frappe.db.get_value(
		parte,
		contraparte,
		["tax_id", "rd_vinculacion", campo_nombre] + (["country"] if parte == "Supplier" else []),
		as_dict=True,
	)
	return frappe._dict(
		tipo=tipo,
		parte=parte,
		contraparte=contraparte,
		nombre=datos.get(campo_nombre),
		identificacion=datos.tax_id,
		pais=datos.get("country"),
		vinculacion=datos.rd_vinculacion,
		**montos,
	)


def asientos(company: str, desde, hasta, partes: dict | None = None) -> list[frappe._dict]:
	"""Asientos validados del período con partes relacionadas que no pagan ni cruzan facturas:
	préstamos, anticipos y otras operaciones. Cargos y abonos por contraparte, sin compensarlos
	(un préstamo dado y cobrado en el año son dos operaciones)."""
	partes = partes or relacionados()
	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	filas = []
	for parte, nombres in partes.items():
		if not nombres:
			continue
		for party, cargos, abonos, documentos in (
			frappe.qb.from_(jea)
			.join(je)
			.on(jea.parent == je.name)
			.select(
				jea.party,
				Sum(jea.debit),
				Sum(jea.credit),
				Count(je.name).distinct(),
			)
			.where(
				(je.company == company)
				& (je.docstatus == 1)
				& (je.posting_date[getdate(desde) : getdate(hasta)])
				& (jea.party_type == parte)
				& (jea.party.isin(nombres))
				& (IfNull(jea.reference_type, "").notin(("Sales Invoice", "Purchase Invoice")))
			)
			.groupby(jea.party)
			.run()
		):
			filas.append(
				_fila(
					parte,
					party,
					ASIENTO,
					documentos=documentos,
					cargos=flt(cargos),
					abonos=flt(abonos),
				)
			)
	return filas
