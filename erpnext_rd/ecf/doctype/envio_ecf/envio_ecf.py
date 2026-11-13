# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext_rd.ecf import conservacion


class EnvioECF(Document):
	def on_trash(self):
		conservacion.no_borrar(self)


def on_doctype_update():
	frappe.db.add_index("Envio ECF", ["company", "estado"])
	frappe.db.add_index("Envio ECF", ["company", "encf"])
	frappe.db.add_index("Envio ECF", ["tipo_documento", "documento"])
	frappe.db.add_index("Envio ECF", ["estado", "proximo_intento"])
