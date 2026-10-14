# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ConfiguracionNominaRD(Document):
	def validate(self):
		self.escala_isr = sorted(self.escala_isr, key=lambda t: flt(t.desde))
		for i, tramo in enumerate(self.escala_isr, start=1):
			tramo.idx = i
			siguiente = self.escala_isr[i] if i < len(self.escala_isr) else None
			if siguiente and not flt(tramo.hasta):
				frappe.throw(
					_("Fila {0} de la escala ISR: solo el último tramo puede no tener límite").format(i)
				)
			if flt(tramo.hasta) and flt(tramo.hasta) <= flt(tramo.desde):
				frappe.throw(_("Fila {0} de la escala ISR: 'Hasta' debe ser mayor que 'Desde'").format(i))
			if siguiente and flt(siguiente.desde) < flt(tramo.hasta):
				frappe.throw(_("Fila {0} de la escala ISR: el tramo se solapa con el siguiente").format(i))
