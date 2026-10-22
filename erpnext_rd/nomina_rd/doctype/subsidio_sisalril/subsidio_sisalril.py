# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from erpnext_rd.nomina_rd import subsidios

# Sin enlace directo a Frappe HR (Dynamic Link sobre un campo Data, `tipo_licencia`) para que la app
# instale y funcione sin él
LICENCIA = "Leave Application"


class SubsidioSISALRIL(Document):
	def validate(self):
		self.tipo_licencia = LICENCIA
		if self.tipo == subsidios.LACTANCIA:
			self.licencia = None
		self._fechas_de_la_licencia()
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

	def _fechas_de_la_licencia(self):
		"""Con la licencia de Frappe HR enlazada, las fechas son las de la solicitud de permiso."""
		if not self.licencia:
			return
		licencia = frappe.db.get_value(
			LICENCIA, self.licencia, ["employee", "from_date", "to_date", "docstatus"], as_dict=True
		)
		if not licencia or licencia.docstatus == 2:
			frappe.throw(_("La licencia {0} no existe o está cancelada.").format(self.licencia))
		if licencia.employee != self.employee:
			frappe.throw(_("La licencia {0} es de otro empleado.").format(self.licencia))
		self.desde, self.hasta = licencia.from_date, licencia.to_date
