# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_reportes import anticipos


class BaseAnticipoISR(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("Los anticipos del ISR solo aplican a empresas de República Dominicana"))
		duplicada = frappe.db.exists(
			anticipos.DOCTYPE,
			{"company": self.company, "ejercicio": self.ejercicio, "name": ("!=", self.name)},
		)
		if duplicada:
			frappe.throw(
				_("Ya existe la base del año {0} para {1}: {2}").format(
					self.ejercicio, self.company, duplicada
				)
			)
		if not self.aplica_desde:
			self.aplica_desde = anticipos.inicio_por_defecto(self.ejercicio)

		if self.regimen == anticipos.EXENTO:
			self.tasa_efectiva = 0
			self.metodo = _("Exento")
			self.cuota_mensual = 0
			return
		if self.ingresos_brutos < 0 or self.impuesto_liquidado < 0:
			frappe.throw(_("Los ingresos y el impuesto no pueden ser negativos"))
		calculo = anticipos.calcular(self.ingresos_brutos, self.impuesto_liquidado, anticipos.tasa_minima())
		self.tasa_efectiva = calculo.tasa_efectiva
		self.metodo = calculo.metodo
		self.cuota_mensual = calculo.cuota
