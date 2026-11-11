# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.licitaciones.proveedor import FAMILIA_UNSPSC


class PerfilProveedorEstado(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(
				_("El perfil de proveedor del Estado solo aplica a empresas de República Dominicana")
			)
		vistas = set()
		for r in self.rubros:
			r.familia_unspsc = (r.familia_unspsc or "").strip()
			if not FAMILIA_UNSPSC.match(r.familia_unspsc):
				frappe.throw(
					_(
						"Fila {0}: la familia UNSPSC tiene 8 dígitos y termina en 0000 (por ejemplo 24110000)."
					).format(r.idx)
				)
			if r.familia_unspsc in vistas:
				frappe.throw(_("Fila {0}: la familia {1} está repetida.").format(r.idx, r.familia_unspsc))
			vistas.add(r.familia_unspsc)
