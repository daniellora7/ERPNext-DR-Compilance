# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.rd_compliance import perfil


class PerfilTributarioRD(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("El perfil tributario solo aplica a empresas de República Dominicana"))
		for i in self.incentivos:
			if i.desde and i.hasta and getdate(i.hasta) < getdate(i.desde):
				frappe.throw(_("Fila {0}: la vigencia termina antes de empezar").format(i.idx))
		if self.tipo_contribuyente != perfil.JURIDICA:
			self.tipo_sociedad = None
		# Título del enlace: lo que muestra el campo «Perfil tributario» de la empresa
		self.resumen = perfil.resumen(self)

	def on_update(self):
		if frappe.db.get_value("Company", self.company, "rd_perfil_tributario") != self.name:
			frappe.db.set_value(
				"Company", self.company, "rd_perfil_tributario", self.name, update_modified=False
			)

	def on_trash(self):
		frappe.db.set_value("Company", self.company, "rd_perfil_tributario", None, update_modified=False)
