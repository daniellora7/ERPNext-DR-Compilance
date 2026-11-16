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
		if self.is_new() and self.regimen in (None, "", anticipos.MENSUAL):
			# Propuesta según el tamaño del perfil (Ley 30-26); se puede cambiar después de guardar
			self.regimen, motivo = anticipos.regimen_por_perfil(self.company, self.ejercicio)
			self.motivo_exencion = self.motivo_exencion or motivo
		if self.regimen == anticipos.TRES_CUOTAS and self.ejercicio < anticipos.desde_ejercicio():
			frappe.throw(
				_(
					"Las tres cuotas de las pequeñas empresas rigen desde la base del ejercicio {0} (Ley 30-26)."
				).format(anticipos.desde_ejercicio())
			)

		if self.regimen == anticipos.EXENTO:
			self.tasa_efectiva = 0
			self.metodo = _("Exento")
			self.cuota_mensual = 0
			return
		if self.ingresos_brutos < 0 or self.impuesto_liquidado < 0:
			frappe.throw(_("Los ingresos y el impuesto no pueden ser negativos"))
		if self.regimen == anticipos.TRES_CUOTAS:
			self.tasa_efectiva = (
				self.impuesto_liquidado * 100 / self.ingresos_brutos if self.ingresos_brutos > 0 else 0
			)
			self.metodo = anticipos.describir_cuotas(anticipos.cuotas_pequenas())
			self.cuota_mensual = self.impuesto_liquidado
			return
		calculo = anticipos.calcular(self.ingresos_brutos, self.impuesto_liquidado, anticipos.tasa_minima())
		self.tasa_efectiva = calculo.tasa_efectiva
		self.metodo = calculo.metodo
		self.cuota_mensual = calculo.cuota
