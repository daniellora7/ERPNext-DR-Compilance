"""Horas extras y horas en feriados según el Código de Trabajo, sobre las de Frappe HR
(extend_doctype_class de *Overtime Slip* en hooks.py).

Frappe HR ya registra las horas extras desde la asistencia (*Overtime Type*, *Overtime Slip*) y las paga
con un *Additional Salary*. En los tipos marcados con `rd_horas_extras` y en empresas RD cambia:

- Valor de la hora: salario ordinario mensual (devengos que cotizan a la TSS de la estructura salarial)
  / días de salario por mes (23.83) / horas de la jornada (8). Frappe HR divide entre los días de pago.
- Art. 203: recargo del 35 % hasta 68 horas a la semana (jornada de 44 + 24 extras) y del 100 % en las
  que pasen de ese límite.
- Horas en feriados y en el día de descanso semanal: recargo del 100 %.
- Art. 204: la parte de las horas extras que cae en la jornada nocturna (art. 149: de 9:00 p. m. a
  7:00 a. m.) suma un 15 % del valor de la hora. Las horas extras se cuentan al final de la jornada: van
  de la salida menos las horas extras hasta la salida (marcación de salida de la asistencia).

Los porcentajes y las horas están en *Configuracion Nomina RD* (editables). Las demás horas extras
(tipos sin la marca) siguen el cálculo de Frappe HR.
"""

import datetime

import frappe
from frappe.utils import flt, get_datetime, get_time

from erpnext_rd.nomina_rd import prestaciones

COMPONENTE = "Horas Extras"
CUENTA_GASTO = "6102"
TIPO = "Horas extras RD"


def parametros():
	conf = frappe.get_cached_doc("Configuracion Nomina RD")
	return frappe._dict(
		dias_mes=flt(conf.dias_salario_mes) or 23.83,
		horas_jornada=flt(conf.horas_jornada) or 8,
		horas_normales=flt(conf.horas_semana_normal) or 44,
		horas_maximo=flt(conf.horas_semana_maximo) or 68,
		recargo=flt(conf.recargo_horas_extras),
		recargo_exceso=flt(conf.recargo_horas_extras_exceso),
		recargo_feriado=flt(conf.recargo_feriado),
		recargo_nocturno=flt(conf.recargo_nocturno),
		inicio_nocturna=get_time(conf.inicio_jornada_nocturna or "21:00:00"),
		fin_nocturna=get_time(conf.fin_jornada_nocturna or "07:00:00"),
	)


def monto(
	horas: float, valor_hora: float, horas_previas_semana: float, feriado: bool, p, nocturnas: float = 0
) -> float:
	"""Pago de unas horas extras de un día, dadas las horas extras ya contadas esa semana y cuántas de
	ellas son nocturnas."""
	recargo_noche = min(nocturnas, horas) * valor_hora * flt(p.recargo_nocturno) / 100 if nocturnas else 0
	if feriado:
		return horas * valor_hora * (1 + p.recargo_feriado / 100) + recargo_noche
	limite = max(p.horas_maximo - p.horas_normales, 0)
	con_recargo = max(min(horas, limite - horas_previas_semana), 0)
	exceso = horas - con_recargo
	return (
		valor_hora * (con_recargo * (1 + p.recargo / 100) + exceso * (1 + p.recargo_exceso / 100))
		+ recargo_noche
	)


def horas_nocturnas(desde, hasta, p) -> float:
	"""Horas del intervalo [desde, hasta] dentro de la jornada nocturna (cruza la medianoche)."""
	desde, hasta = get_datetime(desde), get_datetime(hasta)
	if hasta <= desde:
		return 0.0
	total = 0.0
	dia = desde.date() - datetime.timedelta(days=1)
	while dia <= hasta.date():
		inicio = datetime.datetime.combine(dia, p.inicio_nocturna)
		fin = datetime.datetime.combine(dia, p.fin_nocturna)
		if fin <= inicio:
			fin += datetime.timedelta(days=1)
		total += max((min(hasta, fin) - max(desde, inicio)).total_seconds(), 0) / 3600
		dia += datetime.timedelta(days=1)
	return total


def nocturnas_de_la_salida(salida, horas: float, p) -> float:
	"""Horas extras nocturnas de un día: las horas extras van al final, hasta la salida."""
	if not salida or not horas:
		return 0.0
	salida = get_datetime(salida)
	return horas_nocturnas(salida - datetime.timedelta(hours=flt(horas)), salida, p)


def crear_componente_y_tipo():
	"""Componente "Horas Extras" (con ISR y TSS, cuenta 6102) y el tipo "Horas extras RD" si Frappe HR
	trae horas extras (Overtime Type). El tipo se crea cuando ya hay devengos que cotizan a la TSS."""
	from erpnext_rd.nomina_rd.salario import _cuenta

	if not frappe.db.exists("DocType", "Overtime Type"):
		return
	if frappe.db.exists("Salary Component", COMPONENTE):
		componente = frappe.get_doc("Salary Component", COMPONENTE)
	else:
		componente = frappe.new_doc("Salary Component")
		componente.update(
			{
				"salary_component": COMPONENTE,
				"salary_component_abbr": "HE",
				"type": "Earning",
				"is_tax_applicable": 1,
				"rd_cotiza_tss": 1,
				"depends_on_payment_days": 0,
				"description": "Horas extras y horas en feriados (arts. 203-205), pagadas desde Overtime Slip",
			}
		)
	cambio = componente.is_new()
	for company in frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name"):
		if any(a.company == company for a in componente.accounts):
			continue
		if cuenta := _cuenta(company, CUENTA_GASTO):
			componente.append("accounts", {"company": company, "account": cuenta})
			cambio = True
	if cambio:
		componente.save(ignore_permissions=True)

	if frappe.db.exists("Overtime Type", TIPO) or not frappe.get_meta("Overtime Type").has_field(
		"rd_horas_extras"
	):
		return
	# Frappe HR pide al menos un componente; en un tipo RD la hora sale de todos los que cotizan
	ordinarios = [c for c in prestaciones.componentes_ordinarios() if c != COMPONENTE]
	if not ordinarios:
		return
	p = parametros()
	tipo = frappe.new_doc("Overtime Type")
	tipo.update(
		{
			"__newname": TIPO,
			"rd_horas_extras": 1,
			"overtime_calculation_method": "Salary Component Based",
			"overtime_salary_component": COMPONENTE,
			"standard_multiplier": 1 + p.recargo / 100,
			"applicable_for_weekend": 1,
			"weekend_multiplier": 1 + p.recargo_feriado / 100,
			"applicable_for_public_holiday": 1,
			"public_holiday_multiplier": 1 + p.recargo_feriado / 100,
		}
	)
	for c in ordinarios:
		tipo.append("applicable_salary_component", {"salary_component": c})
	tipo.insert(ignore_permissions=True)
