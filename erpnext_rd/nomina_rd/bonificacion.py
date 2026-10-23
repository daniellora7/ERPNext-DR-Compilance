"""Bonificación: participación de los trabajadores en los beneficios (arts. 223-227 del Código de Trabajo).

- Monto a repartir: el porcentaje de la configuración (10 %) de la utilidad neta del ejercicio, antes
  del ISR y de las bonificaciones de directores y gerentes. Sin utilidad, no hay bonificación.
- Tope de cada trabajador: días de salario ordinario según su antigüedad al cierre (45 con menos de 3
  años, 60 desde 3 años; editables), en proporción a los meses trabajados en el ejercicio. Salario
  ordinario = promedio de los recibos del último año (`prestaciones.salario_diario`, / 23.83).
- Si el monto a repartir no alcanza para todos los topes, se reparte en proporción a ellos (factor =
  monto / suma de topes); si sobra, cada uno recibe su tope.
- Pago: entre 90 y 120 días después del cierre (art. 224). Gravada para el ISR, fuera del salario
  cotizable de la TSS (art. 192) y con el 0.5 % de INFOTEP del empleado (Ley 116-80), que calcula el
  recibo (`salario.INFOTEP_EMPLEADO`).

Empresas exentas (art. 226: agrícolas, industriales, forestales y mineras en sus primeros 3 años,
agrícolas pequeñas, zonas francas) simplemente no crean el documento.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from erpnext_rd.nomina_rd import prestaciones

DIAS_LIMITE_PAGO = 120
# Tipos de empleo de Frappe HR que no suelen ser contratos por tiempo indefinido (art. 223)
NO_INDEFINIDOS = ("Contract", "Intern", "Apprentice")


def parametros():
	conf = frappe.get_cached_doc("Configuracion Nomina RD")
	return frappe._dict(
		porcentaje=flt(conf.bonificacion_porcentaje) or 10,
		anios=cint(conf.bonificacion_anios) or 3,
		dias_menor=flt(conf.bonificacion_dias_menor) or 45,
		dias_mayor=flt(conf.bonificacion_dias_mayor) or 60,
	)


def fecha_limite(hasta):
	return add_days(getdate(hasta), DIAS_LIMITE_PAGO)


def calcular_filas(company: str, desde, hasta) -> list[dict]:
	"""Una fila por trabajador que laboró en el ejercicio, con su tope."""
	p = parametros()
	desde, hasta = getdate(desde), getdate(hasta)
	filas = []
	for e in frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ("<=", hasta)},
		fields=["name", "employee_name", "date_of_joining", "relieving_date", "employment_type"],
		order_by="employee_name",
	):
		if e.relieving_date and getdate(e.relieving_date) < desde:
			continue
		fin = min(getdate(e.relieving_date), hasta) if e.relieving_date else hasta
		meses = min(prestaciones.meses_de_servicio(max(getdate(e.date_of_joining), desde), fin), 12)
		if not meses:
			continue  # menos de un mes completo en el ejercicio
		servicio = prestaciones.meses_de_servicio(e.date_of_joining, fin)
		dias = p.dias_mayor if servicio >= p.anios * 12 else p.dias_menor
		observaciones = []
		try:
			mensual, diario = prestaciones.salario_diario(e.name, fin)
		except frappe.ValidationError:
			frappe.clear_last_message()
			mensual = diario = 0.0
			observaciones.append(_("Sin recibos ni asignación de estructura salarial: sin tope"))
		if e.employment_type in NO_INDEFINIDOS:
			observaciones.append(
				_("Tipo de empleo {0}: la bonificación es para contratos por tiempo indefinido").format(
					_(e.employment_type)
				)
			)
		if e.relieving_date and getdate(e.relieving_date) <= hasta:
			observaciones.append(_("Salió en el ejercicio: se le paga en proporción al tiempo trabajado"))
		filas.append(
			{
				"employee": e.name,
				"employee_name": e.employee_name,
				"meses": meses,
				"anios_servicio": flt(servicio / 12, 1),
				"salario_mensual": mensual,
				"salario_diario": diario,
				"dias": dias,
				"tope": flt(diario * dias * meses / 12, 2),
				"monto": 0.0,
				"observacion": "\n".join(observaciones),
			}
		)
	return filas


def repartir(filas, fondo: float) -> tuple[float, float]:
	"""Pone el monto de cada fila. Devuelve (suma de topes, factor)."""
	total_topes = flt(sum(flt(f.get("tope")) for f in filas), 2)
	factor = min(flt(fondo) / total_topes, 1.0) if total_topes and flt(fondo) > 0 else 0.0
	for f in filas:
		monto = flt(flt(f.get("tope")) * factor, 2)
		if isinstance(f, dict):
			f["monto"] = monto
		else:
			f.monto = monto
	return total_topes, flt(factor, 6)


@frappe.whitelist()
def utilidad_contable(company: str, desde: str | date, hasta: str | date) -> float:
	"""Ingresos menos gastos del ejercicio según la contabilidad (para proponer la utilidad neta; el
	usuario la ajusta: antes del ISR y de las bonificaciones de directores y gerentes)."""
	# Leer la empresa no basta (el rol Employee puede): solo quien prepara la bonificación ve la utilidad
	frappe.has_permission("Bonificacion RD", "create", throw=True)
	frappe.has_permission("Company", doc=company, throw=True)
	gl = frappe.qb.DocType("GL Entry")
	cuenta = frappe.qb.DocType("Account")
	filas = (
		frappe.qb.from_(gl)
		.join(cuenta)
		.on(gl.account == cuenta.name)
		.select(cuenta.root_type, frappe.query_builder.functions.Sum(gl.credit - gl.debit).as_("neto"))
		.where(
			(gl.company == company)
			& (gl.is_cancelled == 0)
			& (gl.posting_date >= getdate(desde))
			& (gl.posting_date <= getdate(hasta))
			& (cuenta.root_type.isin(["Income", "Expense"]))
		)
		.groupby(cuenta.root_type)
	).run(as_dict=True)
	return flt(sum(flt(f.neto) for f in filas), 2)
