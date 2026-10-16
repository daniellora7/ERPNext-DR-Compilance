# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import bonificacion, hrms_instalado

PAGO = "Additional Salary"


class BonificacionRD(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("La bonificación RD solo aplica a empresas de República Dominicana."))
		if not self.porcentaje:
			self.porcentaje = bonificacion.parametros().porcentaje
		self.fondo = flt(max(flt(self.utilidad_neta), 0) * flt(self.porcentaje) / 100, 2)
		if self.hasta:
			self.fecha_limite = bonificacion.fecha_limite(self.hasta)
		self.total_topes, self.factor = bonificacion.repartir(self.empleados, self.fondo)
		self.total = flt(sum(flt(f.monto) for f in self.empleados), 2)
		if self.fecha_pago and self.hasta and getdate(self.fecha_pago) > getdate(self.fecha_limite):
			frappe.msgprint(
				_("La fecha de pago pasa del plazo del art. 224 ({0}).").format(
					frappe.format_value(self.fecha_limite, "Date")
				),
				indicator="orange",
				alert=True,
			)

	@frappe.whitelist()
	def calcular(self):
		"""Llena el reparto con los trabajadores del ejercicio (reemplaza las filas)."""
		if not (self.company and self.desde and self.hasta):
			frappe.throw(_("Indique la empresa y el ejercicio fiscal."))
		self.set("empleados", [])
		for fila in bonificacion.calcular_filas(self.company, self.desde, self.hasta):
			self.append("empleados", fila)
		self.validate()

	def before_submit(self):
		if not hrms_instalado():
			frappe.throw(_("El pago de la bonificación en la nómina requiere Frappe HR."))
		if not self.total:
			frappe.throw(_("No hay bonificación que pagar: revise la utilidad neta y el reparto."))

	def on_submit(self):
		for fila in self.empleados:
			if not flt(fila.monto):
				continue
			salida = frappe.db.get_value("Employee", fila.employee, "relieving_date")
			if salida and getdate(salida) < getdate(self.fecha_pago):
				fila.db_set("observacion", _("Ya salió: pagar fuera de la nómina"))
				continue
			pago = frappe.get_doc(
				{
					"doctype": PAGO,
					"employee": fila.employee,
					"company": self.company,
					"salary_component": self.componente,
					"amount": fila.monto,
					"payroll_date": self.fecha_pago,
					"overwrite_salary_structure_amount": 0,
					"ref_doctype": self.doctype,
					"ref_docname": self.name,
				}
			)
			pago.flags.ignore_permissions = True
			pago.insert()
			pago.submit()
			fila.db_set({"tipo_pago": PAGO, "additional_salary": pago.name})

	def on_cancel(self):
		for fila in self.empleados:
			if fila.additional_salary and frappe.db.get_value(PAGO, fila.additional_salary, "docstatus") == 1:
				pago = frappe.get_doc(PAGO, fila.additional_salary)
				pago.flags.ignore_permissions = True
				pago.cancel()
