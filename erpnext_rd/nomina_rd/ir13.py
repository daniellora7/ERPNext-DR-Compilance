"""Resumen IR-13: retenciones de ISR a asalariados del año, para revisar antes de aceptar.

Como el IR-3, la DGII no recibe un IR-13 llenado a mano: lo arma con los IR-3 del año (que salen de la
nómina enviada a la TSS). El empleador lo consulta en la Oficina Virtual (Declaraciones Juradas →
Declaración IR-13), revisa el detalle en Excel y lo acepta a más tardar el 15 de marzo del año siguiente.
No se puede rectificar: los errores se corrigen en la nómina de la TSS y en los IR-3 del mes, antes
de aceptarlo (después de aceptado, los cambios en los IR-3 ya no se reflejan).

Este resumen suma los doce meses del Resumen IR-3 (`ir3.obtener`): por empleado o por mes.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from erpnext_rd.nomina_rd import feriados, ir3

MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
MONTOS = ("renta", "aportes_tss", "renta_neta", "isr", "isr_retenido", "diferencia", "exentos")
POR_EMPLEADO = "Por empleado"
POR_MES = "Por mes"


def fecha_limite(anio) -> date:
	"""15 de marzo del año siguiente; si cae en fin de semana o feriado, el siguiente día laborable."""
	return feriados.dia_habil(date(int(anio) + 1, 3, 15))


def meses(company: str, anio) -> list[list[dict]]:
	return [ir3.obtener(company, anio, mes) for mes in range(1, 13)]


def por_empleado(datos: list[list[dict]]) -> list[dict]:
	filas = {}
	for mes, filas_mes in enumerate(datos, start=1):
		for f in filas_mes:
			e = filas.setdefault(
				f["employee"],
				{
					"employee": f["employee"],
					"employee_name": f["employee_name"],
					"documento": f["documento"],
					"meses": 0,
					**dict.fromkeys(MONTOS, 0.0),
					"_con_diferencia": [],
				},
			)
			e["meses"] += 1
			e["documento"] = f["documento"] or e["documento"]
			for campo in MONTOS:
				e[campo] += flt(f[campo])
			if abs(flt(f["diferencia"])) > ir3.TOLERANCIA:
				e["_con_diferencia"].append(MESES[mes - 1])
	resultado = []
	for e in filas.values():
		for campo in MONTOS:
			e[campo] = flt(e[campo], 2)
		meses_dif = e.pop("_con_diferencia")
		e["_avisos"] = (
			_("Diferencia entre la escala y lo retenido en: {0}").format(", ".join(meses_dif))
			if meses_dif
			else ""
		)
		resultado.append(e)
	return sorted(resultado, key=lambda e: e["employee_name"] or "")


def por_mes(datos: list[list[dict]]) -> list[dict]:
	resultado = []
	for mes, filas_mes in enumerate(datos, start=1):
		fila = {"mes": MESES[mes - 1], "asalariados": len(filas_mes)}
		for campo in MONTOS:
			fila[campo] = flt(sum(flt(f[campo]) for f in filas_mes), 2)
		con_dif = sum(1 for f in filas_mes if abs(flt(f["diferencia"])) > ir3.TOLERANCIA)
		fila["_avisos"] = (
			_("Sin recibos: IR-3 en cero")
			if not filas_mes
			else _("{0} asalariado(s) con diferencias").format(con_dif)
			if con_dif
			else ""
		)
		resultado.append(fila)
	return resultado


def _columnas(vista: str) -> list[dict]:
	def col(fieldname, label, fieldtype="Currency", width=130, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	if vista == POR_MES:
		inicio = [col("mes", "Mes", "Data", 80), col("asalariados", "Asalariados", "Int", 100)]
	else:
		inicio = [
			col("employee", "Empleado", "Link", 130, options="Employee"),
			col("employee_name", "Nombre", "Data", 200),
			col("documento", "Documento", "Data", 120),
			col("meses", "Meses", "Int", 70),
		]
	return [
		*inicio,
		col("renta", "Remuneraciones gravadas"),
		col("aportes_tss", "AFP y SFS del empleado"),
		col("renta_neta", "Renta neta"),
		col("isr", "ISR según escala"),
		col("isr_retenido", "ISR retenido (recibos)"),
		col("diferencia", "Diferencia", width=110),
		col("exentos", "Ingresos exentos", width=120),
		col("_avisos", "Observaciones", "Data", 300),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	vista = filters.vista or POR_EMPLEADO
	if not (filters.company and filters.anio):
		return _columnas(vista), []
	datos = meses(filters.company, filters.anio)
	empleados = por_empleado(datos)
	filas = por_mes(datos) if vista == POR_MES else empleados
	isr = sum(e["isr"] for e in empleados)
	retenido = sum(e["isr_retenido"] for e in empleados)
	con_diferencias = sum(1 for e in empleados if e["_avisos"])
	limite = formatdate(fecha_limite(filters.anio))

	resumen = [
		{"label": _("Asalariados"), "value": len(empleados), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Remuneraciones gravadas"),
			"value": sum(e["renta"] for e in empleados),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{"label": _("ISR según escala"), "value": isr, "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("ISR retenido en recibos"),
			"value": retenido,
			"datatype": "Currency",
			"indicator": "Orange" if con_diferencias else "Green",
		},
		{
			"label": _("Ingresos exentos"),
			"value": sum(e["exentos"] for e in empleados),
			"datatype": "Currency",
			"indicator": "Blue",
		},
	]
	mensaje = _(
		"La DGII arma el IR-13 con los IR-3 del año. Consúltelo en la Oficina Virtual (Declaraciones "
		"Juradas → Declaración IR-13), compare el Excel del detalle con este resumen y acéptelo a más "
		"tardar el {0}. No se puede rectificar: corrija antes la nómina en la TSS y los IR-3 del mes."
	).format(limite)
	if con_diferencias:
		mensaje += " " + _("{0} asalariado(s) con diferencias entre la escala y lo retenido.").format(
			con_diferencias
		)
	return _columnas(vista), filas, mensaje, None, resumen
