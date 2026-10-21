"""Regalía pascual (salario de Navidad, arts. 219-222 del Código de Trabajo) de diciembre.

No es un documento propio: cada regalía es un *Gratuity* de Frappe HR con la regla "Regalía RD", igual
que la regalía proporcional de una salida. Con *Pagar por nómina* el Gratuity crea un *Additional
Salary* del componente "Regalía Pascual" (exento de ISR y sin TSS) en el recibo de diciembre; si no, se
paga aparte con su asiento. En el archivo de la TSS va como ingreso exento (código 01).

- Monto: la duodécima parte de los salarios ordinarios del año (`prestaciones.regalia_proporcional`
  con corte al 31 de diciembre): recibos aprobados del año y, para los meses que aún no tienen recibo
  (normalmente diciembre), la base de la última asignación de estructura salarial.
- Se paga a más tardar el 20 de diciembre (art. 219). Exenta de ISR sin importar el monto
  (art. 222, Ley 204-97) y no cotiza a la TSS.
- Quien salió en el año cobra la regalía proporcional en su liquidación final: aquí solo se muestra.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import hrms_instalado, prestaciones

COMPONENTE = "Regalía Pascual"
CUENTA_GASTO = "6105"
DIA_LIMITE = 20  # de diciembre (art. 219)
DIA_PAGO = 15  # propuesto: cae en la primera quincena y en la nómina mensual de diciembre
ROLES = ("HR Manager", "HR User", "System Manager")
ESTADOS = {"Draft": "Borrador", "Unpaid": "Aprobada", "Paid": "Pagada", "Submitted": "Aprobada"}


def fecha_limite(anio) -> date:
	return date(int(anio), 12, DIA_LIMITE)


def regla() -> str | None:
	return frappe.db.get_value("Gratuity Rule", {"rd_prestacion": prestaciones.REGALIA, "disable": 0}, "name")


def _empleados(company: str, anio: int) -> list:
	inicio, fin = date(anio, 1, 1), date(anio, 12, 31)
	empleados = frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ("<=", fin)},
		fields=["name", "employee_name", "date_of_joining", "relieving_date", "status"],
		order_by="employee_name",
	)
	return [e for e in empleados if not e.relieving_date or getdate(e.relieving_date) >= inicio]


def _regalias_creadas(company: str, anio: int) -> dict[str, frappe._dict]:
	"""Gratuity "Regalía RD" no cancelados del año (por fecha de pago en nómina o de contabilización)."""
	reglas = frappe.get_all("Gratuity Rule", filters={"rd_prestacion": prestaciones.REGALIA}, pluck="name")
	creadas = {}
	if not reglas:
		return creadas
	for g in frappe.get_all(
		"Gratuity",
		filters={"company": company, "gratuity_rule": ("in", reglas), "docstatus": ("<", 2)},
		fields=[
			"name",
			"employee",
			"amount",
			"status",
			"posting_date",
			"pay_via_salary_slip",
			"payroll_date",
		],
		order_by="creation",
	):
		fecha = g.payroll_date if cint(g.pay_via_salary_slip) and g.payroll_date else g.posting_date
		if getdate(fecha).year == anio:
			creadas[g.employee] = g
	return creadas


def obtener(company: str, anio) -> list[dict]:
	"""Una fila por empleado del año con su regalía y el Gratuity que la paga, si ya existe."""
	if not hrms_instalado():
		frappe.throw(_("La regalía se paga con los Gratuity de Frappe HR, que no está instalado."))
	anio = int(anio)
	fin = date(anio, 12, 31)
	creadas = _regalias_creadas(company, anio)
	filas = []
	for emp in _empleados(company, anio):
		corte = min(getdate(emp.relieving_date), fin) if emp.relieving_date else fin
		r = prestaciones.regalia_proporcional(emp.name, corte)
		g = creadas.get(emp.name)
		avisos = []
		salio = bool(emp.relieving_date) and getdate(emp.relieving_date) <= fin
		if salio:
			avisos.append(
				_("Salió el {0}: la regalía proporcional va en su liquidación final").format(
					formatdate(emp.relieving_date)
				)
			)
		if r.meses_estimados and not salio:
			avisos.append(
				_("{0} mes(es) sin recibo estimados con el salario base").format(flt(r.meses_estimados, 1))
			)
		if not r.monto:
			avisos.append(_("Sin recibos aprobados ni asignación de estructura salarial en el año"))
		if g and abs(flt(g.amount) - r.monto) > 1:
			avisos.append(
				_("El Gratuity tiene {0}: se calculó con los recibos de ese momento").format(
					frappe.format_value(g.amount, "Currency")
				)
			)
		filas.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"date_of_joining": emp.date_of_joining,
				"relieving_date": emp.relieving_date,
				"meses": r.meses,
				"salarios_del_anio": r.salarios_del_anio,
				"meses_estimados": r.meses_estimados,
				"regalia": r.monto,
				"gratuity": g.name if g else None,
				"estado": _(ESTADOS.get(g.status, g.status)) if g else "" if salio else _("Por crear"),
				"_salio": salio,
				"_avisos": "; ".join(avisos),
			}
		)
	return filas


@frappe.whitelist()
def crear_regalias(
	company: str,
	anio: int,
	payroll_date: str | None = None,
	pay_via_salary_slip: int | bool = 1,
	salary_component: str | None = None,
	expense_account: str | None = None,
	payable_account: str | None = None,
	mode_of_payment: str | None = None,
) -> dict:
	"""Crea en borrador el Gratuity de la regalía de cada empleado activo que aún no lo tiene.

	Quedan en borrador para revisarlos y aprobarlos (desde la lista, en bloque); al aprobar, los que se
	pagan por nómina crean el Additional Salary del recibo de diciembre."""
	frappe.only_for(ROLES)
	if not es_empresa_rd(company):
		frappe.throw(_("La regalía pascual RD solo aplica a empresas de República Dominicana."))
	nombre_regla = regla()
	if not nombre_regla:
		frappe.throw(_("No existe una regla de Gratuity activa marcada como Regalía RD."))
	por_nomina = cint(pay_via_salary_slip)
	anio = int(anio)
	fecha = getdate(payroll_date) if payroll_date else date(anio, 12, DIA_PAGO)
	if por_nomina and not (salary_component or frappe.db.exists("Salary Component", COMPONENTE)):
		frappe.throw(_("Indique el componente de nómina de la regalía."))

	creadas, omitidas = [], 0
	for f in obtener(company, anio):
		if f["gratuity"] or f["_salio"] or not f["regalia"]:
			omitidas += 1
			continue
		doc = frappe.new_doc("Gratuity")
		doc.update(
			{
				"employee": f["employee"],
				"company": company,
				"gratuity_rule": nombre_regla,
				"posting_date": fecha,
				"pay_via_salary_slip": por_nomina,
				"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
			}
		)
		if por_nomina:
			doc.payroll_date = fecha
			doc.salary_component = salary_component or COMPONENTE
		else:
			doc.expense_account = expense_account or _cuenta_gasto(company)
			doc.payable_account = payable_account
			doc.mode_of_payment = mode_of_payment
		doc.insert()
		creadas.append(doc.name)
	return {"creadas": creadas, "omitidas": omitidas}


def _cuenta_gasto(company: str) -> str | None:
	from erpnext_rd.nomina_rd.salario import _cuenta

	return _cuenta(company, CUENTA_GASTO)


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------


def _columnas() -> list[dict]:
	def col(fieldname, label, fieldtype="Currency", width=130, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("employee", "Empleado", "Link", 130, options="Employee"),
		col("employee_name", "Nombre", "Data", 200),
		col("date_of_joining", "Ingreso", "Date", 100),
		col("relieving_date", "Salida", "Date", 100),
		col("meses", "Meses del año", "Int", 100),
		col("salarios_del_anio", "Salarios ordinarios del año", width=170),
		col("meses_estimados", "Meses estimados", "Float", 110),
		col("regalia", "Regalía (1/12)"),
		col("gratuity", "Gratuity", "Link", 150, options="Gratuity"),
		col("estado", "Estado", "Data", 100),
		col("_avisos", "Observaciones", "Data", 360),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio):
		return _columnas(), []
	filas = obtener(filters.company, filters.anio)
	activos = [f for f in filas if not f["_salio"]]
	por_crear = sum(1 for f in activos if not f["gratuity"] and f["regalia"])
	limite = formatdate(fecha_limite(filters.anio))

	resumen = [
		{"label": _("Empleados activos"), "value": len(activos), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Regalía de diciembre"),
			"value": sum(f["regalia"] for f in activos),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Por crear"),
			"value": por_crear,
			"datatype": "Int",
			"indicator": "Orange" if por_crear else "Green",
		},
	]
	mensaje = _(
		"El salario de Navidad es la duodécima parte de los salarios ordinarios del año y se paga a más "
		"tardar el {0} (art. 219). Está exento de ISR y no cotiza a la TSS (art. 222); en el archivo de la "
		"TSS va como ingreso exento. Con «Crear regalías» se crean en borrador los Gratuity de los "
		"empleados activos que no la tienen; revíselos y apruébelos antes de la nómina de diciembre."
	).format(limite)
	return _columnas(), filas, mensaje, None, resumen


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------


def crear_componente():
	"""Componente "Regalía Pascual" (exento de ISR, no cotiza a la TSS, cuenta 6105 del catálogo DGII)."""
	if frappe.db.exists("Salary Component", COMPONENTE):
		componente = frappe.get_doc("Salary Component", COMPONENTE)
	else:
		componente = frappe.new_doc("Salary Component")
		componente.update(
			{
				"salary_component": COMPONENTE,
				"salary_component_abbr": "REG",
				"type": "Earning",
				"is_tax_applicable": 0,
				"rd_cotiza_tss": 0,
				"depends_on_payment_days": 0,
				"description": "Salario de Navidad (arts. 219-222 del Código de Trabajo), pagado con el "
				"Gratuity de la regla Regalía RD",
			}
		)
	cambio = componente.is_new()
	for company in frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name"):
		if any(a.company == company for a in componente.accounts):
			continue
		if cuenta := _cuenta_gasto(company):
			componente.append("accounts", {"company": company, "account": cuenta})
			cambio = True
	if cambio:
		componente.save(ignore_permissions=True)
