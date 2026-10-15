"""Gratuity de Frappe HR con el cálculo de las prestaciones RD (override_doctype_class en hooks.py).

Solo cambia el monto cuando la regla está marcada como prestación RD (`rd_prestacion`) y la empresa
es dominicana; lo demás (asiento, pago, estado, liquidación final) sigue siendo de HRMS.
"""

import frappe
from frappe.utils import flt
from hrms.payroll.doctype.gratuity.gratuity import Gratuity

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import prestaciones


class GratuityRD(Gratuity):
	def tipo_prestacion_rd(self) -> str | None:
		if not (self.gratuity_rule and es_empresa_rd(self.company)):
			return None
		return frappe.db.get_value("Gratuity Rule", self.gratuity_rule, "rd_prestacion") or None

	def calculate_work_experience_and_amount(self) -> dict:
		tipo = self.tipo_prestacion_rd()
		if not tipo:
			return super().calculate_work_experience_and_amount()

		componentes = frappe.get_all(
			"Gratuity Applicable Component", filters={"parent": self.gratuity_rule}, pluck="salary_component"
		)
		r = prestaciones.calcular(self.employee, tipo, componentes=componentes)
		self.rd_meses_servicio = r.meses
		self.rd_dias = r.dias
		self.rd_salario_promedio = r.salario_mensual
		self.rd_salario_diario = r.salario_diario
		return {
			"current_work_experience": flt(
				r.meses / prestaciones.MESES_POR_ANIO, self.precision("current_work_experience")
			),
			"amount": r.monto,
		}
