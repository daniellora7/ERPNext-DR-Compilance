# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

"""Soporte para pedir la compensación o el reembolso del saldo a favor del ITBIS de un exportador
(Fase 8.4).

Base (Comunidad de Ayuda de la DGII, CA4923 y CA1430, leídas el 2026-11-13; Código Tributario art.
350, Norma General 12-22 art. 3 y Ley 30-26 art. 52): el exportador puede pedir el saldo a favor
generado por sus exportaciones, del período o acumulado, desde la Oficina Virtual («Devolución y
Compensación de ITBIS»). Solo cuentan las exportaciones con el expediente cerrado en la DGA. Pide
haber enviado el 607 con las facturas de exportación y el 606 con el ITBIS adelantado, estar al día y
tener la marca de exportador; la DGII puede pedir la carta firmada, la certificación de la DGA y los
DUA sellados.

El reporte junta, mes a mes, lo que la solicitud necesita, con los mismos cálculos del resumen del
IT-1: exportaciones, ventas locales, la parte de las exportaciones en las ventas, el ITBIS adelantado
deducible y el saldo a favor. La DGII no publica cómo repartir el saldo cuando también hay ventas
locales: el monto a pedir lo decide el contador.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_rd.dgii_reportes import declaraciones


def meses(company: str, anio: int, saldo_favor_inicial: float = 0) -> list[dict]:
	"""Un renglón por mes con datos; el saldo a favor de cada mes pasa al siguiente, como en el IT-1."""
	filas, saldo = [], flt(saldo_favor_inicial)
	for mes in range(1, 13):
		r = declaraciones.resumen_it1(company, anio, mes, saldo_favor_anterior=saldo)
		ventas = flt(r.ventas_brutas - r.notas_credito)
		if not (ventas or r.itbis_compras or saldo):
			continue
		filas.append(
			{
				"mes": f"{anio}-{mes:02d}",
				"exportaciones": flt(r.exportaciones, 2),
				"ventas_locales": flt(ventas - r.exportaciones, 2),
				"porcentaje_exportacion": flt(100 * r.exportaciones / ventas, 2) if ventas else 0,
				"itbis_facturado": flt(r.itbis_facturado - r.itbis_notas_credito, 2),
				"itbis_deducible": flt(r.itbis_deducible, 2),
				"saldo_anterior": flt(saldo, 2),
				"itbis_a_pagar": flt(r.itbis_a_pagar, 2),
				"saldo_a_favor": flt(r.nuevo_saldo_favor, 2),
			}
		)
		saldo = flt(r.nuevo_saldo_favor)
	return filas


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio):
		return columnas(), []
	filas = meses(filters.company, cint(filters.anio), flt(filters.saldo_favor_inicial))
	exportaciones = sum(f["exportaciones"] for f in filas)
	ventas = exportaciones + sum(f["ventas_locales"] for f in filas)
	mensaje = _(
		"Saldo a favor del ITBIS con los mismos cálculos del resumen del IT-1. La solicitud se hace en la "
		"Oficina Virtual (Devolución y Compensación de ITBIS) y solo cuentan las exportaciones con el "
		"expediente cerrado en la DGA. Antes de pedirla: 606 y 607 enviados, obligaciones al día y la "
		"certificación de la DGA y los DUA sellados a mano. Con ventas locales, el monto a pedir lo decide "
		"el contador: la DGII no publica cómo repartir el saldo."
	)
	resumen = [
		{
			"label": _("Exportaciones del año"),
			"value": exportaciones,
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Parte de las exportaciones en las ventas"),
			"value": flt(100 * exportaciones / ventas, 2) if ventas else 0,
			"datatype": "Percent",
			"indicator": "Blue",
		},
		{
			"label": _("Saldo a favor al último mes"),
			"value": filas[-1]["saldo_a_favor"] if filas else 0,
			"datatype": "Currency",
			"indicator": "Green",
		},
	]
	return columnas(), filas, mensaje, None, resumen


def columnas() -> list[dict]:
	def moneda(fieldname, label, width=140):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": "Currency", "width": width}

	return [
		{"fieldname": "mes", "label": _("Mes"), "fieldtype": "Data", "width": 90},
		moneda("exportaciones", "Exportaciones"),
		moneda("ventas_locales", "Ventas locales"),
		{
			"fieldname": "porcentaje_exportacion",
			"label": _("% exportación"),
			"fieldtype": "Percent",
			"width": 110,
		},
		moneda("itbis_facturado", "ITBIS facturado"),
		moneda("itbis_deducible", "ITBIS adelantado deducible", 180),
		moneda("saldo_anterior", "Saldo a favor anterior", 160),
		moneda("itbis_a_pagar", "ITBIS a pagar"),
		moneda("saldo_a_favor", "Saldo a favor", 140),
	]
