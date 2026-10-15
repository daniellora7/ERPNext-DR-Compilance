# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class ConfiguracionNominaRD(Document):
	def validate(self):
		# Una escala por año: se ordena por año y tramo, y cada escala se revisa por separado
		self.escala_isr = sorted(self.escala_isr, key=lambda t: (cint(t.anio), flt(t.desde)))
		for i, tramo in enumerate(self.escala_isr, start=1):
			tramo.idx = i
			siguiente = self.escala_isr[i] if i < len(self.escala_isr) else None
			if siguiente and cint(siguiente.anio) != cint(tramo.anio):
				siguiente = None
			if siguiente and not flt(tramo.hasta):
				frappe.throw(
					_("Fila {0} de la escala ISR {1}: solo el último tramo puede no tener límite").format(
						i, tramo.anio
					)
				)
			if flt(tramo.hasta) and flt(tramo.hasta) <= flt(tramo.desde):
				frappe.throw(
					_("Fila {0} de la escala ISR {1}: 'Hasta' debe ser mayor que 'Desde'").format(
						i, tramo.anio
					)
				)
			if siguiente and flt(siguiente.desde) < flt(tramo.hasta):
				frappe.throw(
					_("Fila {0} de la escala ISR {1}: el tramo se solapa con el siguiente").format(
						i, tramo.anio
					)
				)
