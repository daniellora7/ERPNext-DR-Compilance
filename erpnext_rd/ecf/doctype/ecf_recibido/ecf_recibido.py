# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext_rd.ecf import conservacion


class ECFRecibido(Document):
	def on_trash(self):
		conservacion.no_borrar(self)


def on_doctype_update():
	frappe.db.add_index("ECF Recibido", ["company", "rnc_emisor", "encf"])
	frappe.db.add_index("ECF Recibido", ["company", "estado", "aprobacion"])
	frappe.db.add_index("ECF Recibido", ["estado", "estado_dgii", "fecha_recepcion"])
	frappe.db.add_index("ECF Recibido", ["factura_compra"])
