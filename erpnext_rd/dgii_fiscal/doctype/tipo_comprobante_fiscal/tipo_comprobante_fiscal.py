# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class TipoComprobanteFiscal(Document):
	def validate(self):
		self.codigo = (self.codigo or "").strip().upper()
		if not re.fullmatch(r"[BE]\d{2}", self.codigo):
			frappe.throw(_("El código debe tener el formato B01 o E31"))
		if self.codigo[0] != self.serie:
			frappe.throw(_("La serie {0} no coincide con el código {1}").format(self.serie, self.codigo))
