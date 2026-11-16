"""IR-1 de la persona física con negocio (Fase 8.8): papel de trabajo con las casillas de la declaración.

Base: instructivo de llenado del IR-1 y anexos (DGII, revisado en marzo de 2026), Código Tributario
art. 296 (escala, según la Ley 30-26, art. 10) y art. 314 (anticipos en tres cuotas, párrafo II):
- 5 = 1 + 2 - 3 - 4; 10 = 5 - 6 - 7 + 8 + 9; 11 = escala de personas físicas del año sobre la casilla 10.
- 6, exención contributiva: el primer tramo de la escala, solo si no reporta costos ni gastos.
- 7, gastos en educación (Ley 179-09): hasta el 10% de 5 - 6 y el 25% de la exención contributiva.
- 16 / 17 = 11 - 12 - 13 - 14 - 15 (diferencia a pagar o saldo a favor).
- Vence el 31 de marzo del año siguiente. Las personas físicas declaran por año calendario.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_rd.nomina_rd import calculos, feriados

DOCTYPE = "Cuadre Fiscal IR1"
TOPE_EDUCACION_RENTA = 10
TOPE_EDUCACION_EXENCION = 25


def exencion_contributiva(anio: int) -> float:
	"""El límite del tramo exento de la escala de personas físicas del año."""
	tramos = calculos.escala_isr(calculos.configuracion(), anio)
	exento = next((t for t in tramos if not flt(t.tasa)), None)
	return flt(exento.hasta) if exento else 0.0


def tope_educacion(renta_neta: float, exencion: float, exencion_del_anio: float) -> float:
	return flt(
		max(
			min(
				(flt(renta_neta) - flt(exencion)) * TOPE_EDUCACION_RENTA / 100,
				flt(exencion_del_anio) * TOPE_EDUCACION_EXENCION / 100,
			),
			0,
		),
		2,
	)


def liquidar(d: frappe._dict, anio: int) -> frappe._dict:
	"""Casillas 5, 6, 10, 11, 16 y 17 a partir de las demás (montos del documento)."""
	r = frappe._dict()
	r.renta_neta = flt(
		flt(d.beneficio_contable) + flt(d.gastos_no_admitidos) - flt(d.ingresos_exentos) - flt(d.dividendos),
		2,
	)
	exento_del_anio = exencion_contributiva(anio)
	r.exencion_contributiva = min(exento_del_anio, max(r.renta_neta, 0)) if cint(d.sin_contabilidad) else 0
	educacion = min(
		flt(d.gastos_educacion), tope_educacion(r.renta_neta, r.exencion_contributiva, exento_del_anio)
	)
	r.gastos_educacion = flt(educacion, 2)
	r.renta_imponible = flt(
		max(
			r.renta_neta
			- r.exencion_contributiva
			- r.gastos_educacion
			+ flt(d.ganancia_acciones)
			+ flt(d.ganancia_inmuebles),
			0,
		),
		2,
	)
	r.impuesto_liquidado = calculos.isr_anual(r.renta_imponible, anio=anio)
	diferencia = flt(
		r.impuesto_liquidado
		- flt(d.anticipos_pagados)
		- flt(d.retenciones)
		- flt(d.otros_pagos)
		- flt(d.saldo_favor_anterior),
		2,
	)
	r.diferencia_pagar = max(diferencia, 0)
	r.saldo_favor = max(-diferencia, 0)
	return r


def fecha_limite(ejercicio: int) -> date:
	return feriados.dia_habil(date(cint(ejercicio) + 1, 3, 31))


def obligacion(company: str, anio: int, mes: int) -> dict | None:
	"""Recordatorio del IR-1 del año que cierra en diciembre, para una persona física del régimen ordinario."""
	from erpnext_rd.rd_compliance import perfil

	if cint(mes) != 12 or not perfil.declara_ir1(company):
		return None
	return {
		"obligacion": _("IR-1 (ISR de persona física) del año {0}").format(anio),
		"vence": fecha_limite(anio),
	}


@frappe.whitelist(methods=["POST"])
def traer_datos(name: str) -> str:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	doc.traer_datos()
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def crear_base_anticipos(name: str) -> str:
	"""Base de los anticipos del año siguiente (tres cuotas, art. 314 párrafo II) con este cuadre."""
	from erpnext_rd.dgii_reportes import anticipos

	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	existente = frappe.db.exists(anticipos.DOCTYPE, {"company": doc.company, "ejercicio": doc.ejercicio})
	if existente:
		return existente
	base = frappe.get_doc(
		{
			"doctype": anticipos.DOCTYPE,
			"company": doc.company,
			"ejercicio": doc.ejercicio,
			"aplica_desde": date(cint(doc.ejercicio) + 1, 4, 1),
			"ingresos_brutos": doc.ingresos,
			# Párrafo IV: el anticipo es sobre el impuesto que no se pagó por retención
			"impuesto_liquidado": max(flt(doc.impuesto_liquidado) - flt(doc.retenciones), 0),
		}
	).insert()
	frappe.msgprint(_("Base de anticipos {0} creada").format(base.name), indicator="green", alert=True)
	return base.name
