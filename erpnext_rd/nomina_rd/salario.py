"""Deducciones de ley en el recibo de nómina (Salary Slip de Frappe HR) para empresas de RD.

Calcula AFP, SFS e ISR del empleado y los aportes del empleador (AFP, SFS, SRL, INFOTEP) con
`calculos.py` y los pone en las filas de los componentes marcados con `rd_concepto_nomina`.

- Salario cotizable TSS: devengos cuyo componente tiene `rd_cotiza_tss`.
- Renta gravable ISR: devengos con `is_tax_applicable` (campo estándar de HR) menos los aportes
  del empleado a la TSS y otras deducciones exentas (`exempted_from_income_tax`).
- Topes y escala son mensuales: en nóminas quincenales o semanales se calcula sobre el
  equivalente mensual y se prorratea.

Se engancha en `SalarySlip.apply_regional_deductions` (regional_overrides, antes de calcular
el neto y también en la vista previa) y en `validate` (por si el país del sistema no es RD).
"""

import frappe
from frappe.utils import cint, flt, getdate, today

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.nomina_rd import calculos, hrms_instalado

AFP = "AFP empleado"
SFS = "SFS empleado"
ISR = "ISR asalariado"
AFP_EMPLEADOR = "AFP empleador"
SFS_EMPLEADOR = "SFS empleador"
SRL = "SRL empleador"
INFOTEP = "INFOTEP empleador"
INFOTEP_EMPLEADO = "INFOTEP empleado"
# Devengo: la bonificación (participación en los beneficios, art. 223) es la base del INFOTEP del empleado
BONIFICACION = "Bonificación (art. 223)"
# Per cápita de los dependientes adicionales del SFS (padres, suegros, hijos mayores), a cargo del trabajador
SFS_DEPENDIENTES = "SFS dependientes adicionales"
CONCEPTOS = [
	AFP,
	SFS,
	ISR,
	AFP_EMPLEADOR,
	SFS_EMPLEADOR,
	SRL,
	INFOTEP,
	INFOTEP_EMPLEADO,
	BONIFICACION,
	SFS_DEPENDIENTES,
]

DEDUCCIONES = {AFP: "afp", SFS: "sfs"}
APORTES_EMPLEADOR = {
	AFP_EMPLEADOR: "afp_empleador",
	SFS_EMPLEADOR: "sfs_empleador",
	SRL: "srl",
	INFOTEP: "infotep",
}

# nombre, abreviatura, tipo, concepto, exento de ISR, cuenta (catálogo DGII), cuenta de pasivo
COMPONENTES = [
	("AFP - Fondo de Pensiones", "AFP", "Deduction", AFP, 1, "210402", None),
	("SFS - Seguro Familiar de Salud", "SFS", "Deduction", SFS, 1, "210402", None),
	("ISR - Retención Asalariados", "ISR", "Deduction", ISR, 0, "210304", None),
	("AFP - Aporte Empleador", "AFP_ER", "Employer Contribution", AFP_EMPLEADOR, 0, "6108", "210402"),
	("SFS - Aporte Empleador", "SFS_ER", "Employer Contribution", SFS_EMPLEADOR, 0, "6108", "210402"),
	("SRL - Riesgos Laborales", "SRL", "Employer Contribution", SRL, 0, "6108", "210402"),
	("INFOTEP - Aporte Empleador", "INFOTEP", "Employer Contribution", INFOTEP, 0, "6109", "210403"),
	# Ley 116-80: el empleado aporta el 0.5 % de las bonificaciones (no es exento del ISR)
	("INFOTEP - Aporte Empleado", "INFOTEP_EE", "Deduction", INFOTEP_EMPLEADO, 0, "210403", None),
	# Gravada para el ISR y fuera del salario cotizable de la TSS (art. 192)
	("Bonificación", "BONIF", "Earning", BONIFICACION, 0, "6104", None),
	# Descuento voluntario: no reduce la renta gravada del ISR
	("SFS - Dependientes adicionales", "SFS_DA", "Deduction", SFS_DEPENDIENTES, 0, "210402", None),
]

# Meses que cubre un recibo según la frecuencia de nómina
MESES_POR_FRECUENCIA = {
	"Monthly": 1,
	"Fortnightly": 0.5,
	"Bimonthly": 0.5,
	"Weekly": 12 / 52,
	"Daily": 12 / 365,
}


def _concepto(componente: str) -> str | None:
	return frappe.get_cached_value("Salary Component", componente, "rd_concepto_nomina")


def _componente_de(concepto: str) -> str | None:
	return frappe.db.get_value("Salary Component", {"rd_concepto_nomina": concepto, "disabled": 0}, "name")


def aplica(slip) -> bool:
	if not (slip.company and es_empresa_rd(slip.company)):
		return False
	return cint(frappe.db.get_single_value("Configuracion Nomina RD", "calcular_deducciones")) == 1


def bases(slip) -> frappe._dict:
	cotizable = gravable = exento = bonificacion = 0.0
	for fila in slip.get("earnings") or []:
		if cint(fila.get("statistical_component")) or cint(fila.get("do_not_include_in_total")):
			continue
		if _concepto(fila.salary_component) == BONIFICACION:
			bonificacion += flt(fila.amount)
		if cint(frappe.get_cached_value("Salary Component", fila.salary_component, "rd_cotiza_tss")):
			cotizable += flt(fila.amount)
		if cint(fila.get("is_tax_applicable")):
			gravable += flt(fila.amount)
	for fila in slip.get("deductions") or []:
		if cint(fila.get("exempted_from_income_tax")) and _concepto(fila.salary_component) not in DEDUCCIONES:
			exento += flt(fila.amount)
	return frappe._dict(
		cotizable=cotizable, gravable=gravable, otras_exenciones=exento, bonificacion=bonificacion
	)


def calcular(slip, conf=None) -> frappe._dict:
	"""Montos del recibo: deducciones del empleado y aportes del empleador."""
	conf = conf or calculos.configuracion()
	meses = MESES_POR_FRECUENCIA.get(slip.get("payroll_frequency") or "Monthly", 1)
	b = bases(slip)

	tss = calculos.aportes_tss(b.cotizable / meses, conf)
	renta_mensual = (b.gravable - b.otras_exenciones) / meses - tss.total_empleado
	# La escala es la del año del período del recibo (en enero 2027 rige la de la Ley 30-26)
	anio = getdate(slip.get("end_date") or slip.get("posting_date") or today()).year
	isr = calculos.isr_mensual(max(renta_mensual, 0.0), conf, anio)

	montos = frappe._dict({concepto: flt(tss[clave] * meses, 2) for concepto, clave in DEDUCCIONES.items()})
	montos.update({concepto: flt(tss[clave] * meses, 2) for concepto, clave in APORTES_EMPLEADOR.items()})
	montos[ISR] = flt(isr * meses, 2)
	montos[INFOTEP_EMPLEADO] = flt(b.bonificacion * flt(conf.infotep_empleado) / 100, 2)
	dependientes = dependientes_adicionales(
		slip.get("employee"), slip.get("start_date"), slip.get("end_date")
	)
	montos[SFS_DEPENDIENTES] = flt(dependientes * per_capita_adicional(conf) * meses, 2)
	return montos


def per_capita_adicional(conf) -> float:
	"""Lo que cobra la TSS al mes por cada dependiente adicional: per cápita del SFS más Fonamat."""
	return flt(conf.sfs_per_capita_adicional) + flt(conf.fonamat_per_capita)


def dependientes_adicionales(employee: str | None, desde, hasta) -> int:
	"""Dependientes adicionales del empleado afiliados en algún día del período del recibo."""
	if not employee:
		return 0
	hasta = getdate(hasta or desde or today())
	desde = getdate(desde or hasta)
	filas = frappe.get_all(
		"Dependiente Adicional SFS",
		filters={"parenttype": "Employee", "parent": employee, "desde": ("<=", hasta)},
		fields=["hasta"],
	)
	return sum(1 for f in filas if not f.hasta or getdate(f.hasta) >= desde)


def _poner(slip, tabla: str, concepto: str, monto: float):
	componente = _componente_de(concepto)
	if not componente:
		return
	filas = [f for f in slip.get(tabla) or [] if f.salary_component == componente]
	if not filas:
		if not monto:
			return
		datos = frappe.get_cached_doc("Salary Component", componente)
		fila = slip.append(tabla, {"salary_component": componente, "abbr": datos.salary_component_abbr})
		fila.exempted_from_income_tax = datos.exempted_from_income_tax
		fila.do_not_include_in_accounts = datos.do_not_include_in_accounts
		filas = [fila]
	for i, fila in enumerate(filas):
		fila.amount = fila.default_amount = monto if i == 0 else 0
		fila.additional_amount = 0
		fila.depends_on_payment_days = 0


def aplicar(slip):
	"""Pone AFP, SFS, ISR y los aportes del empleador en el recibo (idempotente)."""
	if not aplica(slip):
		return
	montos = calcular(slip)
	for concepto in (AFP, SFS, ISR, INFOTEP_EMPLEADO, SFS_DEPENDIENTES):
		_poner(slip, "deductions", concepto, montos[concepto])
	if slip.meta.has_field("employer_contributions"):
		for concepto in APORTES_EMPLEADOR:
			_poner(slip, "employer_contributions", concepto, montos[concepto])


def deducciones_regionales(slip):
	"""regional_overrides: SalarySlip.apply_regional_deductions (antes de calcular el neto)."""
	aplicar(slip)


def al_validar_recibo(doc, method=None):
	"""doc_events: Salary Slip -> validate. Cubre sitios cuyo país del sistema no es RD."""
	if not aplica(doc):
		return
	antes = [(f.salary_component, flt(f.amount)) for f in doc.deductions]
	aplicar(doc)
	if antes != [(f.salary_component, flt(f.amount)) for f in doc.deductions]:
		doc.set_precision_for_component_amounts()
		doc.set_net_pay()


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------


def crear_componentes():
	"""Crea los componentes de nómina de ley (si no existen) y les asigna las cuentas del catálogo
	DGII en cada empresa RD que lo tenga."""
	if not hrms_instalado():
		return
	empresas = frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name")
	for nombre, abbr, tipo, concepto, exento, cuenta, pasivo in COMPONENTES:
		if frappe.db.exists("Salary Component", {"rd_concepto_nomina": concepto}):
			doc = frappe.get_doc("Salary Component", {"rd_concepto_nomina": concepto})
		elif frappe.db.exists("Salary Component", nombre):
			doc = frappe.get_doc("Salary Component", nombre)
			doc.rd_concepto_nomina = concepto
		else:
			doc = frappe.new_doc("Salary Component")
			doc.update(
				{
					"salary_component": nombre,
					"salary_component_abbr": abbr,
					"type": tipo,
					"rd_concepto_nomina": concepto,
					"exempted_from_income_tax": exento,
					"depends_on_payment_days": 0,
					"remove_if_zero_valued": 1,
					"description": "Calculado por ERPNext RD según la Configuración Nómina RD",
				}
			)
			if tipo == "Earning":
				# Devengo de ley: gravado para el ISR, fuera del salario cotizable de la TSS
				doc.update(
					{
						"is_tax_applicable": 1,
						"rd_cotiza_tss": 0,
						"description": "Bonificación de ley (art. 223), pagada con el documento Bonificación RD",
					}
				)
		for company in empresas:
			if any(a.company == company for a in doc.accounts):
				continue
			fila = {"company": company, "account": _cuenta(company, cuenta)}
			if pasivo:
				fila["liability_account"] = _cuenta(company, pasivo)
			if fila["account"]:
				doc.append("accounts", fila)
		doc.save(ignore_permissions=True)


def _cuenta(company: str, numero: str) -> str | None:
	return frappe.db.get_value("Account", {"company": company, "account_number": numero, "is_group": 0})
