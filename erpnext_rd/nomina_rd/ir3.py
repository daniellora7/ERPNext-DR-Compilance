"""Resumen IR-3: retenciones de ISR a asalariados del mes, para revisar antes de presentar.

La DGII no recibe un IR-3 llenado a mano: lo arma con la nómina enviada a la TSS (archivo de
autodeterminación) y el empleador lo revisa con el IR-4 (detalle por asalariado) y lo presenta en la
Oficina Virtual a más tardar el día 10 del mes siguiente. Si no hubo retenciones, se presenta en cero.

Este resumen hace el mismo cálculo con los datos del archivo de la TSS (`tss.obtener`): renta del mes
(salario ISR + otras remuneraciones) menos los aportes del empleado a la TSS (AFP y SFS con topes,
sobre el salario SS), escala anual del ISR de *Configuracion Nomina RD* llevada al mes. Lo compara con
el ISR retenido en los recibos para encontrar diferencias antes de que la DGII liquide.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, flt, formatdate

from erpnext_rd.nomina_rd import calculos, tss

TOLERANCIA = 1.0  # pesos: redondeos de quincenas y semanas


def obtener(company: str, anio, mes) -> list[dict]:
	conf = calculos.configuracion()
	filas = []
	for f in tss.obtener(company, anio, mes):
		if not f["con_recibo"]:
			continue
		aportes = calculos.aportes_tss(f["salario_ss"], conf)
		renta = f["salario_isr"] + f["otras_remuneraciones"]
		renta_neta = max(renta - aportes.total_empleado, 0.0)
		isr = flt(calculos.isr_mensual(renta_neta, conf), 2)
		avisos = [a for a in f["_avisos"].split("; ") if a]
		if abs(isr - f["isr_retenido"]) > TOLERANCIA:
			avisos.insert(
				0,
				_("Por la escala corresponden {0}; en los recibos se retuvo {1}").format(
					frappe.format_value(isr, "Currency"), frappe.format_value(f["isr_retenido"], "Currency")
				),
			)
		filas.append(
			{
				"employee": f["employee"],
				"employee_name": f["employee_name"],
				"documento": f["documento"],
				"renta": flt(renta, 2),
				"aportes_tss": flt(aportes.total_empleado, 2),
				"renta_neta": flt(renta_neta, 2),
				"isr": isr,
				"isr_retenido": f["isr_retenido"],
				"diferencia": flt(isr - f["isr_retenido"], 2),
				"exentos": flt(f["regalia"] + f["prestaciones"], 2),
				"_avisos": "; ".join(avisos),
			}
		)
	return filas


def fecha_limite(anio, mes) -> date:
	"""Día 10 del mes siguiente (si cae en fin de semana o feriado, la DGII lo corre al día laborable)."""
	return add_months(date(int(anio), int(mes), 10), 1)


def _columnas() -> list[dict]:
	def col(fieldname, label, fieldtype="Currency", width=130, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("employee", "Empleado", "Link", 130, options="Employee"),
		col("employee_name", "Nombre", "Data", 200),
		col("documento", "Documento", "Data", 120),
		col("renta", "Remuneraciones gravadas"),
		col("aportes_tss", "AFP y SFS del empleado"),
		col("renta_neta", "Renta neta"),
		col("isr", "ISR según escala"),
		col("isr_retenido", "ISR retenido (recibos)"),
		col("diferencia", "Diferencia", width=110),
		col("exentos", "Ingresos exentos", width=120),
		col("_avisos", "Observaciones", "Data", 360),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio and filters.mes):
		return _columnas(), []
	filas = obtener(filters.company, filters.anio, filters.mes)
	isr = sum(f["isr"] for f in filas)
	retenido = sum(f["isr_retenido"] for f in filas)
	diferencias = sum(1 for f in filas if abs(f["diferencia"]) > TOLERANCIA)
	limite = formatdate(fecha_limite(filters.anio, filters.mes))

	resumen = [
		{"label": _("Asalariados"), "value": len(filas), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Remuneraciones gravadas"),
			"value": sum(f["renta"] for f in filas),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{"label": _("ISR a pagar (según escala)"), "value": isr, "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("ISR retenido en recibos"),
			"value": retenido,
			"datatype": "Currency",
			"indicator": "Orange" if diferencias else "Green",
		},
	]
	if not filas:
		mensaje = _(
			"No hay recibos de nómina aprobados en este período. Si no hubo asalariados ni retenciones, "
			"presente el IR-3 en cero (Oficina Virtual → Declaraciones en Cero) a más tardar el {0}."
		).format(limite)
	else:
		mensaje = _(
			"La DGII arma el IR-3 con la nómina enviada a la TSS. Envíe el archivo de autodeterminación, "
			"descargue el IR-4 en la Oficina Virtual, compárelo con este resumen y presente el IR-3 a más "
			"tardar el {0}."
		).format(limite)
		if diferencias:
			mensaje += " " + _("{0} asalariado(s) con diferencias entre la escala y lo retenido.").format(
				diferencias
			)
	return _columnas(), filas, mensaje, None, resumen
