"""Vacaciones del Código de Trabajo (arts. 177-182) con los permisos de Frappe HR.

- Tipo de permiso "Vacaciones RD" (*Leave Type*, marcado con `rd_vacaciones`): cuenta días laborables
  (sin feriados ni días de descanso) y se puede pagar con *Leave Encashment*.
- Cada aniversario se asigna (*Leave Allocation*) el período de vacaciones del año cumplido: 14 días,
  18 desde los cinco años (tramos editables en *Configuracion Nomina RD*). Se activa en la configuración.
- Las vacaciones solo se pagan en dinero al terminar el contrato (art. 182). El *Leave Encashment* de
  una empresa RD (`leave_encashment_rd.LeaveEncashmentRD`) paga los días pendientes de la asignación
  vigente más la proporción del año incompleto (art. 180), con el salario diario de las prestaciones
  (promedio del último año / 23.83). La liquidación final de Frappe HR ya incluye los Leave Encashment.
"""

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import add_days, add_years, flt, getdate, today

from erpnext_rd.dgii_fiscal.ncf import PAIS
from erpnext_rd.nomina_rd import hrms_instalado, prestaciones

TIPO_PERMISO = "Vacaciones RD"
COMPONENTE = "Vacaciones"
CUENTA_GASTO = "6106"


def tipo_vacaciones() -> str | None:
	return frappe.db.get_value("Leave Type", {"rd_vacaciones": 1}, "name")


def _tramos():
	return frappe.get_cached_doc("Configuracion Nomina RD").get("tramos_vacaciones")


def dias_por_anio(meses: int) -> float:
	"""Días del período de vacaciones al cumplir `meses` de servicio (múltiplo de 12)."""
	return prestaciones.dias_de_prestacion(meses, _tramos())


def dias_proporcionales(meses: int) -> float:
	"""Días de la parte del año que no se completó (art. 180): solo cuentan los meses desde el último aniversario."""
	return prestaciones.dias_de_prestacion(meses % prestaciones.MESES_POR_ANIO, _tramos())


# ---------------------------------------------------------------------------
# Asignación por aniversario
# ---------------------------------------------------------------------------


def asignar_vacaciones(fecha=None, empresas: list[str] | None = None) -> list[str]:
	"""Asigna el período de vacaciones a los empleados activos de empresas RD que cumplieron un año más
	de servicio y aún no lo tienen. Idempotente (tarea diaria). Devuelve las asignaciones creadas."""
	if not hrms_instalado() or not frappe.db.get_single_value(
		"Configuracion Nomina RD", "asignar_vacaciones"
	):
		return []
	tipo = tipo_vacaciones()
	if not tipo:
		return []

	fecha = getdate(fecha or today())
	empresas = empresas or frappe.get_all("Company", filters={"country": PAIS}, pluck="name")
	creadas = []
	for empleado in frappe.get_all(
		"Employee",
		filters={"status": "Active", "company": ("in", empresas), "date_of_joining": ("is", "set")},
		fields=["name", "date_of_joining"],
	):
		# Años cumplidos a la fecha: el período empieza el día del aniversario
		anios = relativedelta(fecha, getdate(empleado.date_of_joining)).years
		if anios < 1:
			continue
		desde = add_years(getdate(empleado.date_of_joining), anios)
		hasta = add_days(add_years(desde, 1), -1)
		if frappe.db.exists(
			"Leave Allocation",
			{
				"employee": empleado.name,
				"leave_type": tipo,
				"docstatus": ("<", 2),
				"from_date": ("<=", hasta),
				"to_date": (">=", desde),
			},
		):
			continue
		asignacion = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": empleado.name,
				"leave_type": tipo,
				"from_date": desde,
				"to_date": hasta,
				"new_leaves_allocated": dias_por_anio(anios * prestaciones.MESES_POR_ANIO),
				"description": _(
					"Vacaciones del año {0} de servicio (art. 177 del Código de Trabajo)"
				).format(anios),
			}
		)
		asignacion.insert(ignore_permissions=True)
		asignacion.submit()
		creadas.append(asignacion.name)
	return creadas


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------


def crear_componente_y_tipo():
	"""Componente de nómina "Vacaciones" (con la cuenta 6106 del catálogo DGII) y el tipo de permiso
	"Vacaciones RD", si faltan. Si el usuario ya marcó otro tipo de permiso como vacaciones RD, se respeta."""
	from erpnext_rd.nomina_rd.salario import _cuenta

	if frappe.db.exists("Salary Component", COMPONENTE):
		componente = frappe.get_doc("Salary Component", COMPONENTE)
	else:
		componente = frappe.new_doc("Salary Component")
		componente.update(
			{
				"salary_component": COMPONENTE,
				"salary_component_abbr": "VAC",
				"type": "Earning",
				"is_tax_applicable": 1,
				"rd_cotiza_tss": 1,
				"depends_on_payment_days": 0,
				"description": "Pago de vacaciones (Leave Encashment del tipo de permiso Vacaciones RD)",
			}
		)
	for company in frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name"):
		if any(a.company == company for a in componente.accounts):
			continue
		if cuenta := _cuenta(company, CUENTA_GASTO):
			componente.append("accounts", {"company": company, "account": cuenta})
	componente.save(ignore_permissions=True)

	if tipo_vacaciones():
		return
	if frappe.db.exists("Leave Type", TIPO_PERMISO):
		frappe.db.set_value("Leave Type", TIPO_PERMISO, "rd_vacaciones", 1)
		return
	frappe.get_doc(
		{
			"doctype": "Leave Type",
			"leave_type_name": TIPO_PERMISO,
			"rd_vacaciones": 1,
			"include_holiday": 0,
			"is_carry_forward": 0,
			"allow_encashment": 1,
			"earning_component": COMPONENTE,
		}
	).insert(ignore_permissions=True)
