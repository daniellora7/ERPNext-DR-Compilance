"""Prestaciones laborales del Código de Trabajo (Ley 16-92): preaviso (art. 76) y auxilio de cesantía (art. 80).

No es un documento propio: se usa el *Gratuity* de Frappe HR (asiento, pago por nómina o por banco,
estado y la *Full and Final Statement* de la salida del empleado). Una *Gratuity Rule* marcada con
`rd_prestacion` cambia solo el cálculo del monto (`gratuity_rd.GratuityRD`):

- Tiempo de servicio en meses completos, de la fecha de ingreso a la de salida (inclusive).
- Días según los tramos de *Configuracion Nomina RD* (editables). Un tramo "por cada año" paga sus
  días por año completo y la fracción que sobra se paga con los tramos de menos de un año.
- Salario diario = salario promedio mensual del último año (art. 85) / 23.83 (configurable).
"""

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate

from erpnext_rd.nomina_rd.salario import MESES_POR_FRECUENCIA

CESANTIA = "Cesantía"
PREAVISO = "Preaviso"
REGLAS = {CESANTIA: "Cesantía RD", PREAVISO: "Preaviso RD"}
TABLAS = {CESANTIA: "tramos_cesantia", PREAVISO: "tramos_preaviso"}

# Valores para inicializar la configuración: desde meses, hasta meses (0 = sin límite), días, por cada año
TRAMOS_PREAVISO = [(3, 6, 7, 0), (6, 12, 14, 0), (12, 0, 28, 0)]
TRAMOS_CESANTIA = [(3, 6, 6, 0), (6, 12, 13, 0), (12, 60, 21, 1), (60, 0, 23, 1)]
TRAMOS_INICIALES = {"tramos_preaviso": TRAMOS_PREAVISO, "tramos_cesantia": TRAMOS_CESANTIA}

MESES_POR_ANIO = 12


def meses_de_servicio(ingreso, salida) -> int:
	"""Meses completos trabajados. La fecha de salida es el último día trabajado, por eso se suma uno."""
	r = relativedelta(add_days(getdate(salida), 1), getdate(ingreso))
	return max(r.years * MESES_POR_ANIO + r.months, 0)


def _en_tramo(tramo, meses: int) -> bool:
	return meses >= tramo.desde_meses and (not tramo.hasta_meses or meses < tramo.hasta_meses)


def dias_de_prestacion(meses: int, tramos) -> float:
	tramo = next((t for t in tramos if _en_tramo(t, meses)), None)
	if not tramo:
		return 0
	if not tramo.por_cada_anio:
		return flt(tramo.dias)
	anios, resto = divmod(meses, MESES_POR_ANIO)
	fraccion = next((t for t in tramos if not t.por_cada_anio and _en_tramo(t, resto)), None)
	return anios * flt(tramo.dias) + (flt(fraccion.dias) if fraccion else 0)


def componentes_ordinarios() -> list[str]:
	"""Si la regla no indica componentes: los ingresos que cotizan a la TSS (sin regalía ni bonos no
	cotizables), que es lo más cercano al salario ordinario del art. 85."""
	return frappe.get_all(
		"Salary Component", filters={"type": "Earning", "rd_cotiza_tss": 1, "disabled": 0}, pluck="name"
	)


def salario_promedio_mensual(empleado: str, salida, componentes: list[str]) -> float:
	"""Promedio mensual de los ingresos ordinarios de los recibos del último año antes de la salida.

	Si trabajó menos de un año se promedia sobre el tiempo que cubren sus recibos. Sin recibos se
	usa la base de su última asignación de estructura salarial."""
	salida = getdate(salida)
	desde = add_days(add_months(salida, -MESES_POR_ANIO), 1)
	recibos = frappe.get_all(
		"Salary Slip",
		filters={"employee": empleado, "docstatus": 1, "end_date": ("between", [desde, salida])},
		fields=["name", "payroll_frequency"],
	)
	if recibos and componentes:
		total = frappe.get_all(
			"Salary Detail",
			filters={
				"parenttype": "Salary Slip",
				"parentfield": "earnings",
				"parent": ("in", [r.name for r in recibos]),
				"salary_component": ("in", componentes),
			},
			fields=[{"SUM": "amount", "as": "total"}],
		)[0].total
		# Meses que cubren los recibos según su frecuencia (quincenal = 1/2), como en salario.py
		meses = min(MESES_POR_ANIO, sum(MESES_POR_FRECUENCIA.get(r.payroll_frequency, 1) for r in recibos))
		if flt(total) and meses:
			return flt(total) / meses

	base = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": empleado, "docstatus": 1, "from_date": ("<=", salida)},
		order_by="from_date desc",
		pluck="base",
		limit=1,
	)
	if base and flt(base[0]):
		return flt(base[0])
	frappe.throw(
		_(
			"No hay recibos de nómina ni asignación de estructura salarial para calcular el salario de {0}."
		).format(frappe.bold(empleado))
	)


def calcular(empleado: str, tipo: str, salida=None, componentes: list[str] | None = None) -> frappe._dict:
	"""Preaviso o cesantía de un empleado a su fecha de salida (por defecto, la del empleado)."""
	conf = frappe.get_cached_doc("Configuracion Nomina RD")
	ingreso, fecha_salida = frappe.db.get_value("Employee", empleado, ["date_of_joining", "relieving_date"])
	salida = salida or fecha_salida
	if not salida:
		frappe.throw(
			_("Indique la fecha de salida (Relieving Date) del empleado {0}.").format(frappe.bold(empleado))
		)

	meses = meses_de_servicio(ingreso, salida)
	dias = dias_de_prestacion(meses, conf.get(TABLAS[tipo]))
	mensual = (
		salario_promedio_mensual(empleado, salida, componentes or componentes_ordinarios()) if dias else 0
	)
	diario = flt(mensual / (flt(conf.dias_salario_mes) or 23.83), 2)
	return frappe._dict(
		meses=meses,
		dias=dias,
		salario_mensual=flt(mensual, 2),
		salario_diario=diario,
		monto=flt(dias * diario, 2),
	)


def crear_reglas():
	"""Crea las reglas "Cesantía RD" y "Preaviso RD" de Gratuity si faltan. Los tramos no van en la
	regla (HRMS los cuenta en años enteros) sino en Configuracion Nomina RD. Sin componentes: se usan
	los ingresos que cotizan a la TSS (`componentes_ordinarios`); el usuario puede elegir otros."""
	for tipo, nombre in REGLAS.items():
		if frappe.db.exists("Gratuity Rule", nombre):
			continue
		regla = frappe.get_doc(
			{
				"doctype": "Gratuity Rule",
				"__newname": nombre,
				"rd_prestacion": tipo,
				"calculate_gratuity_amount_based_on": "Current Slab",
				"work_experience_calculation_function": "Take Exact Completed Years",
				"total_working_days_per_year": 365,
				"minimum_year_for_gratuity": 0,
			}
		)
		regla.flags.ignore_mandatory = True
		regla.insert(ignore_permissions=True)


def inicializar_tramos(conf) -> bool:
	"""Llena los tramos de la ley en la configuración si están vacíos. Devuelve si cambió algo."""
	cambio = False
	for tabla, tramos in TRAMOS_INICIALES.items():
		if conf.get(tabla):
			continue
		for desde, hasta, dias, por_anio in tramos:
			conf.append(
				tabla, {"desde_meses": desde, "hasta_meses": hasta, "dias": dias, "por_cada_anio": por_anio}
			)
		cambio = True
	return cambio
