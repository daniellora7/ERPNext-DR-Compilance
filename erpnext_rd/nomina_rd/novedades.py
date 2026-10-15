"""Archivo de novedades del período (NV) de la TSS para el SUIR Plus.

Formato: «Instructivo para construcción de archivos de autodeterminación y novedades» v6.0 de la TSS.
El detalle es el de la autodeterminación (`tss.linea_detalle`) con 18 posiciones más después de la
clave de nómina: tipo de novedad (2), fecha de inicio (DDMMAAAA) y fecha de fin (DDMMAAAA, solo
licencias y vacaciones). 330 posiciones, 384 con ingresos exentos al final.

Novedades que salen de Frappe HR / ERPNext en el mes:

- IN (ingreso): empleados cuya fecha de ingreso cae en el mes.
- SA (salida): empleados cuya fecha de salida (*Relieving Date*) cae en el mes; lleva la regalía y el
  preaviso / cesantía del mes como ingresos exentos.
- AD (actualización de datos, p. ej. cambio de salario): *Salary Structure Assignment* aprobada que
  empieza en el mes, de un empleado que ya tenía otra.
- VC, LV, LM, LD (vacaciones y licencias): *Leave Application* aprobada que empieza en el mes, del tipo
  de permiso marcado con `rd_novedad_tss`.

Los salarios deben ser los del período (la proporción devengada si entra o sale a mitad de mes): se
toman del recibo aprobado del mes y, si aún no existe, se estiman con la base de la asignación de
estructura salarial prorrateada por días (con observación).

A diferencia de la autodeterminación, los archivos de novedades no se sustituyen: cada envío suma sus
novedades, por eso el reporte permite filtrar por empleado o tipo para no enviar dos veces la misma.
"""

import re
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, formatdate, getdate

from erpnext_rd.nomina_rd import feriados, prestaciones, tss

PROCESO = "NV"
INGRESO = "IN"
SALIDA = "SA"
ACTUALIZACION = "AD"
NOMBRES = {
	INGRESO: "Ingreso",
	SALIDA: "Salida",
	ACTUALIZACION: "Actualización de datos (salario)",
	"VC": "Vacaciones",
	"LV": "Licencia voluntaria",
	"LM": "Licencia por maternidad",
	"LD": "Licencia por discapacidad",
}
LONGITUD = tss.LONGITUD_DETALLE + 18


def _en(fecha, desde: date, hasta: date) -> bool:
	return bool(fecha) and desde <= getdate(fecha) <= hasta


def _eventos(company: str, desde: date, hasta: date) -> list[frappe._dict]:
	"""(empleado, tipo, inicio, fin) de las novedades del mes."""
	eventos = []
	empleados = frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ("<=", hasta)},
		fields=["name", "date_of_joining", "relieving_date"],
	)
	ingresan = set()
	for e in empleados:
		if _en(e.date_of_joining, desde, hasta):
			ingresan.add(e.name)
			eventos.append(frappe._dict(employee=e.name, tipo=INGRESO, inicio=getdate(e.date_of_joining)))
		if _en(e.relieving_date, desde, hasta):
			eventos.append(frappe._dict(employee=e.name, tipo=SALIDA, inicio=getdate(e.relieving_date)))

	# Cambio de salario: nueva asignación de estructura de alguien que ya tenía una (no la del ingreso)
	asignaciones = frappe.get_all(
		"Salary Structure Assignment",
		filters={"company": company, "docstatus": 1, "from_date": ("between", (desde, hasta))},
		fields=["employee", "from_date"],
		order_by="from_date",
	)
	vistos = set()
	for a in asignaciones:
		if a.employee in ingresan or a.employee in vistos:
			continue
		if frappe.db.exists(
			"Salary Structure Assignment",
			{"employee": a.employee, "docstatus": 1, "from_date": ("<", a.from_date)},
		):
			vistos.add(a.employee)
			eventos.append(frappe._dict(employee=a.employee, tipo=ACTUALIZACION, inicio=getdate(a.from_date)))

	# Vacaciones y licencias
	if frappe.get_meta("Leave Type").has_field("rd_novedad_tss"):
		tipos = {
			t.name: t.rd_novedad_tss[:2]
			for t in frappe.get_all(
				"Leave Type", filters={"rd_novedad_tss": ("is", "set")}, fields=["name", "rd_novedad_tss"]
			)
		}
		if tipos:
			for p in frappe.get_all(
				"Leave Application",
				filters={
					"company": company,
					"docstatus": 1,
					"status": "Approved",
					"leave_type": ("in", list(tipos)),
					"from_date": ("between", (desde, hasta)),
				},
				fields=["employee", "leave_type", "from_date", "to_date"],
			):
				eventos.append(
					frappe._dict(
						employee=p.employee,
						tipo=tipos[p.leave_type],
						inicio=getdate(p.from_date),
						fin=getdate(p.to_date),
					)
				)
	return eventos


def _salario_estimado(fila: dict, evento, ingreso, salida, desde: date, hasta: date) -> list[str]:
	"""Sin recibo del mes: base de la asignación por los días del mes en que trabajó."""
	inicio = max(getdate(ingreso), desde) if ingreso else desde
	fin = min(getdate(salida), hasta) if salida else hasta
	dias_mes = date_diff(hasta, desde) + 1
	dias = max(date_diff(fin, inicio) + 1, 0)
	base = prestaciones.base_asignada(evento.employee, fin)
	if not base:
		return [_("Sin recibo del mes ni asignación de estructura salarial: salario en cero")]
	monto = flt(base * dias / dias_mes, 2)
	fila["salario_ss"] = fila["salario_isr"] = monto
	fila["otras_remuneraciones"] = 0.0
	return [
		_("Sin recibo aprobado del mes: salario estimado con la base ({0} de {1} días)").format(
			dias, dias_mes
		)
	]


def obtener(company: str, anio, mes, employee: str | None = None, tipo: str | None = None) -> list[dict]:
	desde, hasta = tss.periodo(anio, mes)
	base = {f["employee"]: f for f in tss.obtener(company, anio, mes)}
	fechas = {
		e.name: e
		for e in frappe.get_all(
			"Employee",
			filters={"company": company},
			fields=["name", "date_of_joining", "relieving_date"],
		)
	}
	filas = []
	for ev in _eventos(company, desde, hasta):
		if (employee and ev.employee != employee) or (tipo and ev.tipo != tipo) or ev.employee not in base:
			continue
		f = dict(base[ev.employee])
		avisos = [a for a in f["_avisos"].split("; ") if a and a != _(tss.SIN_RECIBO)]
		if not f["con_recibo"]:
			e = fechas[ev.employee]
			avisos[:0] = _salario_estimado(f, ev, e.date_of_joining, e.relieving_date, desde, hasta)
		if ev.tipo != SALIDA:
			# Los ingresos exentos (regalía, prestaciones) se informan con la salida o en la autodeterminación
			f["regalia"] = f["prestaciones"] = 0.0
		f.update(
			{
				"tipo_novedad": ev.tipo,
				"novedad": _(NOMBRES.get(ev.tipo, ev.tipo)),
				"fecha_inicio": ev.inicio,
				"fecha_fin": ev.get("fin"),
				"exentos": flt(f["regalia"] + f["prestaciones"], 2),
				"_en_txt": 1 if f["tipo_documento"] and re.fullmatch(r"\d{3}", f["clave_nomina"]) else 0,
				"_avisos": "; ".join(avisos),
			}
		)
		filas.append(f)
	return sorted(filas, key=lambda f: (f["fecha_inicio"], f["employee_name"] or ""))


def _fecha(valor) -> str:
	return getdate(valor).strftime("%d%m%Y") if valor else " " * 8


def linea_novedad(f: dict) -> str:
	detalle = tss.linea_detalle(f)
	linea = (
		detalle[:4] + f["tipo_novedad"] + _fecha(f["fecha_inicio"]) + _fecha(f.get("fecha_fin")) + detalle[4:]
	)
	if len(linea) not in (LONGITUD, LONGITUD + 54):
		frappe.throw(_("Registro de novedad con longitud {0} para {1}").format(len(linea), f["employee"]))
	return linea


def generar_txt(
	company: str, anio, mes, employee: str | None = None, tipo: str | None = None
) -> tuple[str, str]:
	rnc = tss.rnc_de(company)
	filas = [f for f in obtener(company, anio, mes, employee, tipo) if f["_en_txt"]]
	if not filas:
		frappe.throw(_("No hay novedades con documento en este período."), title=_("Sin registros"))
	return tss.armar_archivo(rnc, PROCESO, anio, mes, [linea_novedad(f) for f in filas])


@frappe.whitelist()
def descargar_txt(company: str, anio, mes, employee: str | None = None, tipo_novedad: str | None = None):
	frappe.only_for(tss.ROLES)
	frappe.has_permission("Company", doc=company, throw=True)
	tss.responder_archivo(*generar_txt(company, anio, mes, employee or None, tipo_novedad or None))


def tercer_dia_habil(anio, mes) -> date:
	fecha = feriados.dia_habil(date(int(anio), int(mes), 1))
	for _i in range(2):
		fecha = feriados.dia_habil(add_days(fecha, 1))
	return fecha


# ---------------------------------------------------------------------------
# Script Report
# ---------------------------------------------------------------------------


def _columnas() -> list[dict]:
	def col(fieldname, label, fieldtype="Data", width=110, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("fecha_inicio", "Fecha", "Date", 100),
		col("novedad", "Novedad", width=160),
		col("employee", "Empleado", "Link", 130, options="Employee"),
		col("employee_name", "Nombre", width=190),
		col("documento", "Documento", width=120),
		col("fecha_fin", "Hasta", "Date", 100),
		col("salario_ss", "Salario SS", "Currency", 120),
		col("salario_isr", "Salario ISR", "Currency", 120),
		col("otras_remuneraciones", "Otras remuneraciones ISR", "Currency", 140),
		col("exentos", "Ingresos exentos", "Currency", 120),
		col("_en_txt", "En el archivo", "Check", 80),
		col("_avisos", "Observaciones", width=360),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio and filters.mes):
		return _columnas(), []
	filas = obtener(filters.company, filters.anio, filters.mes, filters.employee, filters.tipo_novedad)
	en_txt = sum(1 for f in filas if f["_en_txt"])
	con_avisos = sum(1 for f in filas if f["_avisos"])
	resumen = [
		{"label": _("Novedades en el archivo"), "value": en_txt, "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Con observaciones"),
			"value": con_avisos,
			"datatype": "Int",
			"indicator": "Orange" if con_avisos else "Green",
		},
	]
	siguiente = date(int(filters.anio) + (int(filters.mes) == 12), int(filters.mes) % 12 + 1, 1)
	mensaje = _(
		"Las novedades del mes se envían en Gestión de archivos del SUIR Plus hasta el {0} (tercer día hábil "
		"del mes siguiente). A diferencia de la autodeterminación, cada archivo de novedades se suma a los "
		"anteriores: filtre por empleado o tipo para no enviar dos veces la misma novedad. Si solo envía la "
		"autodeterminación, la TSS genera sola los movimientos que detecte."
	).format(formatdate(tercer_dia_habil(siguiente.year, siguiente.month)))
	return _columnas(), filas, mensaje, None, resumen
