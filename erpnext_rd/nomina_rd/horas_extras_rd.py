"""Overtime Slip de Frappe HR con las horas extras del Código de Trabajo (extend_doctype_class en
hooks.py: Frappe la combina con la clase de HRMS). Solo cambia el cálculo en los tipos marcados con
`rd_horas_extras` y en empresas RD; la lógica y los parámetros están en `horas_extras.py`."""

import frappe
from frappe.utils import cstr, flt, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import prestaciones
from erpnext_rd.nomina_rd.horas_extras import monto, nocturnas_de_la_salida, parametros


class OvertimeSlipRD:
	def _es_rd(self, overtime_type) -> bool:
		return bool((self.overtime_types.get(overtime_type) or {}).get("rd"))

	def _bulk_load_overtime_types(self, overtime_type_names):
		tipos = super()._bulk_load_overtime_types(overtime_type_names)
		if (
			tipos
			and es_empresa_rd(self.company)
			and frappe.get_meta("Overtime Type").has_field("rd_horas_extras")
		):
			for nombre in frappe.get_all(
				"Overtime Type", filters={"name": ("in", list(tipos)), "rd_horas_extras": 1}, pluck="name"
			):
				tipos[nombre]["rd"] = 1
		return tipos

	def _calculate_component_based_hourly_rate(self, overtime_type, standard_working_hours):
		if not self._es_rd(overtime_type):
			return super()._calculate_component_based_hourly_rate(overtime_type, standard_working_hours)
		if not hasattr(self, "_cached_salary_slip"):
			from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
				get_assigned_salary_structure,
			)

			self._cached_salary_slip = self._make_salary_slip(
				get_assigned_salary_structure(self.employee, self.start_date)
			)
		ordinarios = set(prestaciones.componentes_ordinarios())
		# Salario del mes completo (default_amount), aunque el recibo de referencia esté prorrateado
		mensual = sum(
			flt(fila.get("default_amount") or fila.amount)
			for fila in self._cached_salary_slip.earnings
			if fila.salary_component in ordinarios and not fila.get("additional_salary")
		)
		p = parametros()
		return mensual / p.dias_mes / p.horas_jornada

	def calculate_overtime_amount(
		self, overtime_type, applicable_hourly_rate, overtime_duration, overtime_date, holiday_date_map
	):
		if not self._es_rd(overtime_type):
			return super().calculate_overtime_amount(
				overtime_type, applicable_hourly_rate, overtime_duration, overtime_date, holiday_date_map
			)
		if applicable_hourly_rate <= 0:
			return 0.0
		feriado = cstr(overtime_date) in holiday_date_map
		semana = tuple(getdate(overtime_date).isocalendar()[:2])
		acumuladas = getattr(self, "_horas_por_semana", {})
		self._horas_por_semana = acumuladas
		previas = acumuladas.get(semana, 0.0)
		if not feriado:
			acumuladas[semana] = previas + flt(overtime_duration)
		p = parametros()
		nocturnas = nocturnas_de_la_salida(
			self._salida(overtime_type, overtime_date, overtime_duration), flt(overtime_duration), p
		)
		return monto(flt(overtime_duration), applicable_hourly_rate, previas, feriado, p, nocturnas)

	def _salida(self, overtime_type, overtime_date, overtime_duration):
		"""Marcación de salida de la asistencia de esa fila de horas extras (para el recargo nocturno)."""
		for fila in self.overtime_details:
			if (
				fila.reference_document
				and fila.overtime_type == overtime_type
				and getdate(fila.date) == getdate(overtime_date)
				and flt(fila.overtime_duration) == flt(overtime_duration)
			):
				return frappe.db.get_value("Attendance", fila.reference_document, "out_time")
		return None
