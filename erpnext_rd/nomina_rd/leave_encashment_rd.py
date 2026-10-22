"""Leave Encashment de Frappe HR con el pago de vacaciones RD al terminar el contrato
(override_doctype_class en hooks.py). Ver `vacaciones.py`."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import prestaciones
from erpnext_rd.nomina_rd.vacaciones import dias_proporcionales

# Frappe HR es opcional: sin él el DocType no existe y hooks.py nunca carga esta clase
try:
	from hrms.hr.doctype.leave_encashment.leave_encashment import LeaveEncashment
except ImportError:
	from frappe.model.document import Document as LeaveEncashment


class LeaveEncashmentRD(LeaveEncashment):
	"""Leave Encashment de Frappe HR: en vacaciones RD agrega la proporción del año incompleto y usa el
	salario diario de las prestaciones. Los demás tipos de permiso y empresas siguen igual."""

	def es_vacaciones_rd(self) -> bool:
		if not (self.leave_type and frappe.db.get_value("Leave Type", self.leave_type, "rd_vacaciones")):
			return False
		company = self.company or frappe.db.get_value("Employee", self.employee, "company")
		return bool(company and es_empresa_rd(company))

	def _salida(self):
		salida = frappe.db.get_value("Employee", self.employee, "relieving_date")
		if not salida:
			frappe.throw(
				_(
					"Las vacaciones solo se pagan en dinero al terminar el contrato (art. 182 del Código de "
					"Trabajo). Indique la fecha de salida (Relieving Date) del empleado {0}."
				).format(frappe.bold(self.employee))
			)
		return getdate(salida)

	def validate(self):
		if self.es_vacaciones_rd():
			self.company = self.company or frappe.db.get_value("Employee", self.employee, "company")
			self.leave_period = self.leave_period or periodo_de_permisos(
				self.company, self.encashment_date or self._salida()
			)
		super().validate()

	@frappe.whitelist()
	def get_leave_details_for_encashment(self):
		super().get_leave_details_for_encashment()
		# En el formulario: propone el período existente (al guardar se crea si falta)
		if self.es_vacaciones_rd() and not self.leave_period:
			self.leave_period = periodo_de_permisos(
				self.company, self.encashment_date or self._salida(), crear=False
			)

	def get_leave_allocation(self):
		asignacion = super().get_leave_allocation()
		# Sin asignación vigente (menos de un año) solo se paga la proporción
		if not asignacion and self.es_vacaciones_rd():
			return frappe._dict()
		return asignacion

	def set_leave_balance(self):
		if not self.es_vacaciones_rd():
			return super().set_leave_balance()

		ingreso = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		meses = prestaciones.meses_de_servicio(ingreso, self._salida())
		self.rd_dias_proporcionales = dias_proporcionales(meses)
		if self.get_leave_allocation():
			super().set_leave_balance()
		else:
			self.leave_balance = 0
			self.leave_allocation = None
		self.leave_balance = flt(self.leave_balance) + flt(self.rd_dias_proporcionales)

	def set_encashment_amount(self):
		if not self.es_vacaciones_rd():
			return super().set_encashment_amount()
		self.rd_salario_promedio, self.rd_salario_diario = prestaciones.salario_diario(
			self.employee, self._salida()
		)
		self.encashment_amount = flt(flt(self.encashment_days) * self.rd_salario_diario, 2)

	# La proporción no viene de una asignación: no se descuenta de ella ni del libro de permisos.
	# Se toma primero la proporción y el resto de la asignación.
	def _dias_de_la_asignacion(self) -> float:
		return max(flt(self.encashment_days) - flt(self.rd_dias_proporcionales), 0)

	def _solo_asignacion(self, metodo):
		dias = self.encashment_days
		self.encashment_days = self._dias_de_la_asignacion()
		try:
			metodo()
		finally:
			self.encashment_days = dias

	def on_submit(self):
		if not self.es_vacaciones_rd():
			return super().on_submit()
		self._solo_asignacion(super().on_submit)

	def on_cancel(self):
		if not self.es_vacaciones_rd():
			return super().on_cancel()
		self._solo_asignacion(super().on_cancel)

	def set_encashed_leaves_in_allocation(self):
		if self.leave_allocation:
			super().set_encashed_leaves_in_allocation()

	def create_leave_ledger_entry(self, submit=True):
		if self.es_vacaciones_rd() and not (self.leave_allocation and self.encashment_days):
			return
		super().create_leave_ledger_entry(submit)


def periodo_de_permisos(company: str, fecha, crear: bool = True) -> str | None:
	"""*Leave Period* de la empresa que cubre la fecha (Frappe HR lo pide en el Leave Encashment).
	Si no hay y `crear`, se crea el del año calendario."""
	fecha = getdate(fecha)
	periodo = frappe.db.get_value(
		"Leave Period",
		{"company": company, "from_date": ("<=", fecha), "to_date": (">=", fecha)},
		"name",
		order_by="is_active desc, from_date desc",
	)
	if periodo or not crear:
		return periodo
	return (
		frappe.get_doc(
			{
				"doctype": "Leave Period",
				"company": company,
				"from_date": f"{fecha.year}-01-01",
				"to_date": f"{fecha.year}-12-31",
				"is_active": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
