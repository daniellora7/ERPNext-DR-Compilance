# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd


class PerfilTributarioRD(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("El perfil tributario solo aplica a empresas de República Dominicana"))
		for i in self.incentivos:
			if i.desde and i.hasta and getdate(i.hasta) < getdate(i.desde):
				frappe.throw(_("Fila {0}: la vigencia termina antes de empezar").format(i.idx))
