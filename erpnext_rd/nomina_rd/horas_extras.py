"""Horas extras y horas en feriados según el Código de Trabajo, sobre las de Frappe HR
(override_doctype_class de *Overtime Slip* en hooks.py).

Frappe HR ya registra las horas extras desde la asistencia (*Overtime Type*, *Overtime Slip*) y las paga
con un *Additional Salary*. En los tipos marcados con `rd_horas_extras` y en empresas RD cambia:

- Valor de la hora: salario ordinario mensual (devengos que cotizan a la TSS de la estructura salarial)
  / días de salario por mes (23.83) / horas de la jornada (8). Frappe HR divide entre los días de pago.
- Art. 203: recargo del 35 % hasta 68 horas a la semana (jornada de 44 + 24 extras) y del 100 % en las
  que pasen de ese límite.
- Horas en feriados y en el día de descanso semanal: recargo del 100 %.

Los porcentajes y las horas están en *Configuracion Nomina RD* (editables). Las demás horas extras
(tipos sin la marca) siguen el cálculo de Frappe HR.
"""

import frappe
from frappe.utils import flt

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
	)


def monto(horas: float, valor_hora: float, horas_previas_semana: float, feriado: bool, p) -> float:
	"""Pago de unas horas extras de un día, dadas las horas extras ya contadas esa semana."""
	if feriado:
		return horas * valor_hora * (1 + p.recargo_feriado / 100)
	limite = max(p.horas_maximo - p.horas_normales, 0)
	con_recargo = max(min(horas, limite - horas_previas_semana), 0)
	exceso = horas - con_recargo
	return valor_hora * (con_recargo * (1 + p.recargo / 100) + exceso * (1 + p.recargo_exceso / 100))


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
