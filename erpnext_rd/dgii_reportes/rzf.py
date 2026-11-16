"""Apoyo para el RZF-01: impuesto sobre las ventas de las zonas francas industriales al mercado local.

Base (DGII, confirmado el 2026-11-16): formulario RZF-01-2012 («Según Ley No. 253-12»), página de
obligaciones fiscales de las zonas francas y Comunidad de Ayuda (CA312 y la consulta «RZF Zona Franca
de exportación»):
- Casilla 1, ventas totales a zonas francas: lo vendido a otras zonas francas.
- Casilla 2, ventas en el mercado local (bienes y servicios a personas físicas y jurídicas): la base.
- Casilla 3 = casilla 2 x 3.5% (`tasa_rzf` en *Configuracion DGII*). Las casillas 4 a 7 (saldos,
  compensaciones, pagos y retenciones) se escriben en el formulario.
- Se presenta a más tardar el día 15 de cada mes.
Las exportaciones no van en el formulario. Una factura es exportación si la dirección del cliente es de
otro país. La base es sin ITBIS (el ITBIS no es venta); la DGII no lo dice expresamente.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day

from erpnext_rd.dgii_fiscal import regimenes
from erpnext_rd.dgii_reportes import declaraciones
from erpnext_rd.nomina_rd import feriados

DIA_VENCE = 15
TASA_POR_DEFECTO = 3.5
ZONAS_FRANCAS = (regimenes.ZONA_FRANCA, regimenes.ZONA_FRANCA_COMERCIAL)

A_ZONAS_FRANCAS = "Ventas a zonas francas (casilla 1)"
MERCADO_LOCAL = "Mercado local (casilla 2)"
EXPORTACION = "Exportación (no va en el RZF-01)"


def tasa() -> float:
	valor = frappe.db.get_single_value("Configuracion DGII", "tasa_rzf")
	return flt(valor) if valor not in (None, "") else TASA_POR_DEFECTO


def vence(anio: int, mes: int):
	return feriados.dia_habil(declaraciones.vencimiento(anio, mes, DIA_VENCE))


def clasificar(regimen_cliente: str | None, pais_direccion: str | None) -> str:
	if regimen_cliente in ZONAS_FRANCAS:
		return A_ZONAS_FRANCAS
	if pais_direccion and pais_direccion != "Dominican Republic":
		return EXPORTACION
	return MERCADO_LOCAL


def liquidar(a_zonas_francas: float, mercado_local: float, tasa_rzf: float) -> frappe._dict:
	return frappe._dict(
		casilla_1=flt(a_zonas_francas, 2),
		casilla_2=flt(mercado_local, 2),
		casilla_3=flt(max(flt(mercado_local), 0) * flt(tasa_rzf) / 100, 2),
	)


def facturas(company: str, anio: int, mes: int) -> list[frappe._dict]:
	"""Facturas de venta aprobadas del mes con su casilla. Las notas de crédito restan."""
	desde = get_first_day(f"{cint(anio):04d}-{cint(mes):02d}-01")
	filas = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": company,
			"docstatus": 1,
			"posting_date": ("between", [desde, get_last_day(desde)]),
		},
		fields=[
			"name",
			"posting_date",
			"customer",
			"customer_name",
			"customer_address",
			"rd_ncf",
			"base_net_total",
		],
		order_by="posting_date, name",
	)
	clientes = {f.customer for f in filas}
	regimen = dict(
		frappe.get_all(
			"Customer",
			filters={"name": ("in", list(clientes))},
			fields=["name", "rd_regimen_especial"],
			as_list=True,
		)
	)
	direcciones = {f.customer_address for f in filas if f.customer_address}
	pais = dict(
		frappe.get_all(
			"Address", filters={"name": ("in", list(direcciones))}, fields=["name", "country"], as_list=True
		)
	)
	for f in filas:
		f.casilla = clasificar(regimen.get(f.customer), pais.get(f.customer_address))
		f.monto = flt(f.base_net_total, 2)
	return filas


def reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "casilla", "label": _("Casilla"), "fieldtype": "Data", "width": 240},
		{
			"fieldname": "name",
			"label": _("Factura"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{"fieldname": "posting_date", "label": _("Fecha"), "fieldtype": "Date", "width": 100},
		{"fieldname": "rd_ncf", "label": _("NCF"), "fieldtype": "Data", "width": 140},
		{"fieldname": "customer_name", "label": _("Cliente"), "fieldtype": "Data", "width": 220},
		{"fieldname": "monto", "label": _("Monto sin ITBIS"), "fieldtype": "Currency", "width": 150},
	]
	if not (filters.company and filters.anio and filters.mes):
		return columnas, []

	if not regimenes.empresa_zona_franca(
		filters.company, get_last_day(f"{cint(filters.anio):04d}-{cint(filters.mes):02d}-01")
	):
		mensaje = _(
			"El RZF-01 es de las zonas francas industriales: agregue el incentivo «{0}» en el perfil tributario."
		).format(regimenes.ZONA_FRANCA)
		return columnas, [], mensaje

	filas = facturas(filters.company, filters.anio, filters.mes)
	total = {
		c: sum(f.monto for f in filas if f.casilla == c)
		for c in (A_ZONAS_FRANCAS, MERCADO_LOCAL, EXPORTACION)
	}
	r = liquidar(total[A_ZONAS_FRANCAS], total[MERCADO_LOCAL], tasa())
	limite = vence(filters.anio, filters.mes)
	orden = {A_ZONAS_FRANCAS: 0, MERCADO_LOCAL: 1, EXPORTACION: 2}
	filas.sort(key=lambda f: (orden[f.casilla], f.posting_date, f.name))
	for f in filas:
		f.casilla = _(f.casilla)
	resumen = [
		{"label": _("1. Ventas a zonas francas"), "value": r.casilla_1, "datatype": "Currency"},
		{"label": _("2. Ventas en el mercado local"), "value": r.casilla_2, "datatype": "Currency"},
		{
			"label": _("3. Impuesto ({0}%)").format(f"{tasa():g}"),
			"value": r.casilla_3,
			"datatype": "Currency",
			"indicator": "Red",
		},
		{"label": _("Vence"), "value": limite, "datatype": "Date", "indicator": "Blue"},
	]
	mensaje = _(
		"Apoyo para el RZF-01 de {0}: ventas del mes sin ITBIS, por casilla. Las ventas a clientes de zonas "
		"francas van en la casilla 1; las exportaciones (dirección del cliente en otro país) no van en el "
		"formulario. Escriba en el formulario los saldos, compensaciones, pagos y retenciones (casillas 4 a "
		"7). Vence el {1}. Verifique los montos con su contador."
	).format(f"{cint(filters.mes):02d}/{filters.anio}", frappe.format(limite, "Date"))
	return columnas, filas, mensaje, None, resumen


def obligacion(company: str, anio: int, mes: int) -> dict | None:
	"""Recordatorio del RZF-01 del período, para una zona franca industrial."""
	if not regimenes.empresa_zona_franca(company, get_last_day(f"{cint(anio):04d}-{cint(mes):02d}-01")):
		return None
	return {
		"obligacion": _("RZF-01 (ventas al mercado local) de {0}/{1}").format(f"{cint(mes):02d}", anio),
		"vence": vence(anio, mes),
	}
