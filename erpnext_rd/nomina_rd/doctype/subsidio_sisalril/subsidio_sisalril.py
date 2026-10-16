# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from erpnext_rd.nomina_rd import subsidios


class SubsidioSISALRIL(Document):
	def validate(self):
		if self.hasta and getdate(self.hasta) < getdate(self.desde):
			frappe.throw(_("'Hasta' no puede ser anterior a 'Desde'"))
		if self.tipo != subsidios.ENFERMEDAD:
			self.atencion = None
		if not flt(self.salario_base) and self.employee and self.company:
			base = subsidios.salario_base(self.tipo, self.employee, self.company, self.desde)
			self.salario_base = base.salario
			self.meses_cotizados = base.meses
			if base.meses < base.requeridos:
				frappe.msgprint(
					_("Solo hay {0} de {1} meses con recibos de nómina antes de la licencia.").format(
						base.meses, base.requeridos
					),
					indicator="orange",
					alert=True,
				)

		calculo = subsidios.calcular(self.tipo, self.desde, self.hasta, self.salario_base, self.atencion)
		self.hasta = calculo.hasta
		self.dias_subsidio = calculo.dias
		self.porcentaje = calculo.porcentaje
		self.monto_mensual = calculo.monto_mensual
		self.monto_estimado = calculo.monto
		if self.tipo == subsidios.LACTANCIA and not calculo.porcentaje and flt(self.salario_base):
			frappe.msgprint(
				_("El salario pasa de tres salarios mínimos: no corresponde subsidio por lactancia."),
				indicator="orange",
				alert=True,
			)
