"""Portal del empleado (/rd-compliance/mi-nomina): volantes de pago, acumulado del año y vacaciones.

Solo para el usuario que tiene un *Employee* activo vinculado (`user_id`) y si Frappe HR está
instalado. Cada método busca el empleado de la sesión: nunca recibe el empleado como parámetro, así
nadie consulta los datos de otro.

- `resumen()`: datos del empleado, volantes aprobados (los últimos 24), acumulado del año (bruto, AFP,
  SFS, ISR y neto), saldo de permisos y solicitudes recientes.
- `volante(name)`: PDF del recibo con el formato *Volante de pago RD*.
- `solicitar_permiso(...)`: crea la *Leave Application* abierta, que aprueba su supervisor en Frappe HR.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_years, date_diff, flt, getdate, today

from erpnext_rd.nomina_rd import hrms_instalado, salario
from erpnext_rd.nomina_rd import volante as volante_rd

ROL = "Employee"
MAXIMO_VOLANTES = 24
MAXIMO_SOLICITUDES = 10


def empleado_de_la_sesion(lanzar: bool = True) -> frappe._dict | None:
	if not hrms_instalado() or frappe.session.user == "Guest":
		if lanzar:
			frappe.throw(_("El portal del empleado no está disponible."), frappe.PermissionError)
		return None
	empleado = frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		["name", "employee_name", "company", "designation", "department", "date_of_joining", "holiday_list"],
		as_dict=True,
	)
	if not empleado and lanzar:
		frappe.throw(_("Su usuario no está vinculado a un empleado activo."), frappe.PermissionError)
	return empleado


def tiene_portal() -> bool:
	return bool(empleado_de_la_sesion(lanzar=False))


@frappe.whitelist()
def resumen() -> dict:
	e = empleado_de_la_sesion()
	hoy = getdate(today())
	volantes = frappe.get_all(
		"Salary Slip",
		filters={"employee": e.name, "docstatus": 1},
		fields=[
			"name",
			"start_date",
			"end_date",
			"posting_date",
			"gross_pay",
			"total_deduction",
			"net_pay",
			"currency",
		],
		order_by="end_date desc",
		limit=MAXIMO_VOLANTES,
	)
	return {
		"empleado": {
			"nombre": e.employee_name,
			"codigo": e.name,
			"empresa": e.company,
			"cargo": e.designation,
			"departamento": e.department,
			"ingreso": e.date_of_joining,
			"antiguedad_dias": date_diff(hoy, e.date_of_joining) if e.date_of_joining else None,
			"proximo_aniversario": proximo_aniversario(e.date_of_joining, hoy),
		},
		"volantes": volantes,
		"acumulado": acumulado(e.name, hoy.year),
		"permisos": permisos(e.name, hoy),
		"solicitudes": frappe.get_all(
			"Leave Application",
			filters={"employee": e.name, "docstatus": ("<", 2)},
			fields=["name", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
			order_by="from_date desc",
			limit=MAXIMO_SOLICITUDES,
		),
		"tipos_permiso": [{"value": t, "label": _(t)} for t in permisos(e.name, hoy, solo_tipos=True)],
	}


def proximo_aniversario(ingreso, hoy):
	if not ingreso:
		return None
	ingreso = getdate(ingreso)
	anios = max(hoy.year - ingreso.year, 0)
	fecha = getdate(add_years(ingreso, anios))
	return fecha if fecha >= hoy else getdate(add_years(ingreso, anios + 1))


def acumulado(employee: str, anio: int) -> dict:
	"""Lo ganado y retenido en el año calendario (base del IR-13): volantes aprobados del año."""
	slip = frappe.qb.DocType("Salary Slip")
	detalle = frappe.qb.DocType("Salary Detail")
	desde, hasta = f"{anio}-01-01", f"{anio}-12-31"
	totales = frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "docstatus": 1, "end_date": ("between", (desde, hasta))},
		fields=[
			{"SUM": "gross_pay", "as": "bruto"},
			{"SUM": "net_pay", "as": "neto"},
			{"COUNT": "name", "as": "volantes"},
		],
	)[0]
	componente = frappe.qb.DocType("Salary Component")
	por_concepto = dict(
		frappe.qb.from_(detalle)
		.join(slip)
		.on(detalle.parent == slip.name)
		.join(componente)
		.on(detalle.salary_component == componente.name)
		.select(componente.rd_concepto_nomina, Sum(detalle.amount))
		.where(
			(slip.employee == employee)
			& (slip.docstatus == 1)
			& (slip.end_date[getdate(desde) : getdate(hasta)])
			& (detalle.parenttype == "Salary Slip")
			& (detalle.parentfield == "deductions")
			& (componente.rd_concepto_nomina.isin((salario.AFP, salario.SFS, salario.ISR)))
		)
		.groupby(componente.rd_concepto_nomina)
		.run()
	)
	return {
		"anio": anio,
		"volantes": totales.volantes or 0,
		"bruto": flt(totales.bruto),
		"afp": flt(por_concepto.get(salario.AFP)),
		"sfs": flt(por_concepto.get(salario.SFS)),
		"isr": flt(por_concepto.get(salario.ISR)),
		"neto": flt(totales.neto),
	}


def permisos(employee: str, hoy, solo_tipos: bool = False):
	"""Saldo por tipo de permiso con asignación vigente (Frappe HR)."""
	# Las funciones internas de get_leave_details: esa pide leer *Leave Type*, que el rol Employee no
	# tiene. El empleado ya es el de la sesión.
	from hrms.hr.doctype.leave_application.leave_application import (
		get_leave_allocation_records,
		get_leave_balance_on,
		get_leaves_for_period,
		get_leaves_pending_approval_for_period,
	)

	asignaciones = get_leave_allocation_records(employee, hoy)
	if solo_tipos:
		return list(asignaciones)
	filas = []
	for tipo, a in asignaciones.items():
		filas.append(
			{
				"tipo": tipo,
				"etiqueta": _(tipo),
				"asignados": flt(a.total_leaves_allocated, 2),
				"tomados": flt(-get_leaves_for_period(employee, tipo, a.from_date, a.to_date), 2),
				"pendientes_aprobar": flt(
					get_leaves_pending_approval_for_period(employee, tipo, a.from_date, a.to_date), 2
				),
				"disponibles": flt(
					get_leave_balance_on(
						employee,
						tipo,
						hoy,
						to_date=a.to_date,
						consider_all_leaves_in_the_allocation_period=True,
					),
					2,
				),
			}
		)
	return filas


@frappe.whitelist()
def volante(name: str):
	"""PDF del volante de pago, solo si es del empleado de la sesión y está aprobado."""
	e = empleado_de_la_sesion()
	if frappe.db.get_value("Salary Slip", name, ["employee", "docstatus"]) != (e.name, 1):
		frappe.throw(_("Volante no encontrado."), frappe.PermissionError)
	formato = volante_rd.FORMATO if frappe.db.exists("Print Format", volante_rd.FORMATO) else None
	frappe.local.response.filename = f"{name}.pdf"
	# Frappe revisa además el permiso de impresión del rol Employee (permiso de usuario sobre su empleado)
	frappe.local.response.filecontent = frappe.get_print("Salary Slip", name, formato, as_pdf=True)
	frappe.local.response.type = "pdf"


@frappe.whitelist(methods=["POST"])
def solicitar_permiso(leave_type: str, desde: str, hasta: str, motivo: str | None = None) -> str:
	"""Crea la solicitud de permiso (abierta) del empleado de la sesión; la aprueba su supervisor."""
	e = empleado_de_la_sesion()
	if leave_type not in permisos(e.name, getdate(today()), solo_tipos=True):
		frappe.throw(_("No tiene días asignados de {0}.").format(leave_type))
	solicitud = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": e.name,
			"company": e.company,
			"leave_type": leave_type,
			"from_date": getdate(desde),
			"to_date": getdate(hasta),
			"description": motivo,
			"status": "Open",
		}
	)
	solicitud.insert()
	return solicitud.name
