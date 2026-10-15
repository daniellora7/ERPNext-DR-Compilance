"""Gratuity de Frappe HR con el cálculo de las prestaciones RD y la regalía proporcional
(override_doctype_class en hooks.py).

Solo cambia el monto cuando la regla está marcada como prestación RD (`rd_prestacion`) y la empresa
es dominicana; lo demás (asiento, pago, estado, liquidación final) sigue siendo de HRMS.
"""

import frappe
from frappe.utils import cint, flt, getdate, today
from hrms.payroll.doctype.gratuity.gratuity import Gratuity

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import prestaciones


class GratuityRD(Gratuity):
	def tipo_prestacion_rd(self) -> str | None:
		if not (self.gratuity_rule and es_empresa_rd(self.company)):
			return None
		return frappe.db.get_value("Gratuity Rule", self.gratuity_rule, "rd_prestacion") or None

	def anio_de_pago(self) -> int:
		fecha = (
			self.payroll_date if cint(self.pay_via_salary_slip) and self.payroll_date else self.posting_date
		)
		return getdate(fecha or today()).year

	def calculate_work_experience_and_amount(self) -> dict:
		tipo = self.tipo_prestacion_rd()
		if not tipo:
			return super().calculate_work_experience_and_amount()

		componentes = frappe.get_all(
			"Gratuity Applicable Component", filters={"parent": self.gratuity_rule}, pluck="salary_component"
		)
		# Regalía de diciembre de un empleado activo: los salarios del año hasta el 31 de diciembre
		salida = (
			prestaciones.corte_regalia(self.employee, self.anio_de_pago())
			if tipo == prestaciones.REGALIA
			else None
		)
		r = prestaciones.calcular(self.employee, tipo, salida=salida, componentes=componentes)
		self.rd_meses_servicio = r.meses
		self.rd_dias = r.dias
		self.rd_salario_promedio = r.salario_mensual
		self.rd_salario_diario = r.salario_diario
		self.rd_salarios_del_anio = r.get("salarios_del_anio") or 0
		return {
			"current_work_experience": flt(
				r.meses / prestaciones.MESES_POR_ANIO, self.precision("current_work_experience")
			),
			"amount": r.monto,
		}
