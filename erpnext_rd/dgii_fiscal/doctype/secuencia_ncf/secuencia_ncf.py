# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_rd.dgii_fiscal.validaciones import DIGITOS_SECUENCIAL


class SecuenciaNCF(Document):
	def validate(self):
		self.serie = frappe.db.get_value("Tipo Comprobante Fiscal", self.tipo_comprobante, "serie")
		maximo = 10 ** DIGITOS_SECUENCIAL[self.serie] - 1

		if self.desde < 1 or self.hasta > maximo:
			frappe.throw(_("El rango debe estar entre 1 y {0} para la serie {1}").format(maximo, self.serie))
		if self.hasta < self.desde:
			frappe.throw(_("'Hasta' no puede ser menor que 'Desde'"))

		if self.is_new() or not self.siguiente:
			self.siguiente = self.siguiente or self.desde
		if not (self.desde <= self.siguiente <= self.hasta + 1):
			frappe.throw(
				_("El siguiente secuencial debe estar entre {0} y {1}").format(self.desde, self.hasta + 1)
			)

		self.disponibles = self.hasta - self.siguiente + 1
		if self.disponibles == 0:
			self.habilitada = 0

		self.validar_solapamiento()

	def validar_solapamiento(self):
		solapada = frappe.db.get_value(
			"Secuencia NCF",
			{
				"name": ("!=", self.name),
				"company": self.company,
				"tipo_comprobante": self.tipo_comprobante,
				"desde": ("<=", self.hasta),
				"hasta": (">=", self.desde),
			},
		)
		if solapada:
			frappe.throw(_("El rango se solapa con la secuencia {0}").format(solapada))
