"""Catálogo de cuentas para empresas de República Dominicana, alineado con la DGII.

- Estructura NIIF para PYMES con los rubros que pide la DGII (IR-2, IT-1, IR-17, IR-3, TSS).
- Activos fijos separados por categoría de depreciación fiscal (Art. 287 del Código Tributario).
- Gastos agrupados por "Tipo de bienes y servicios" del formato 606 e ingresos por
  "Tipo de ingreso" del 607: la cuenta usada en la factura sugiere el tipo.
- Cuentas de impuestos marcadas con su concepto fiscal (ITBIS, retenciones, ISC, propina)
  para clasificar los montos en los reportes 606 / 607.

Se aplica por empresa y solo a empresas con país República Dominicana que aún no tienen
movimientos (ver `aplicar_catalogo_dgii`). Las de otros países conservan su catálogo.
"""

import frappe
from frappe import _
from frappe.utils import cint

from erpnext_rd.dgii_fiscal.cuentas_dgii import CUENTAS
from erpnext_rd.dgii_reportes import estados_ir2
from erpnext_rd.nomina_rd import hrms_instalado

PAIS = "Dominican Republic"
NOMBRE_CATALOGO = "República Dominicana - DGII"


ROOT_TYPE = {"1": "Asset", "2": "Liability", "3": "Equity", "4": "Income", "5": "Expense", "6": "Expense"}

# Campo de Company -> número de cuenta del catálogo
CUENTAS_POR_DEFECTO = {
	"default_cash_account": "110101",
	"default_bank_account": "110201",
	"default_receivable_account": "110301",
	"default_payable_account": "210101",
	"default_advance_received_account": "210501",
	"default_advance_paid_account": "110307",
	"default_income_account": "4101",
	"default_expense_account": "5101",
	"default_inventory_account": "110401",
	"stock_adjustment_account": "5105",
	"stock_received_but_not_billed": "210201",
	"asset_received_but_not_billed": "210202",
	"default_provisional_account": "210203",
	"write_off_account": "6606",
	"round_off_account": "6607",
	"exchange_gain_loss_account": "6704",
	"unrealized_exchange_gain_loss_account": "6705",
	"disposal_account": "4501",
	"depreciation_expense_account": "6401",
	"accumulated_depreciation_account": "120202",
	"capital_work_in_progress_account": "120109",
	# Frappe HR
	"default_payroll_payable_account": "210401",
	"default_employee_advance_account": "110303",
	"default_expense_claim_payable_account": "210408",
}
CUENTA_RECLAMOS_GASTOS = "6111"

# Plantillas de impuestos. Las tasas son editables por el usuario después (cambian por ley).
# (titulo, por_defecto, [(tipo_cargo, cuenta, tasa, fila_base, deducir, descripcion)])
PLANTILLAS_VENTA = [
	("ITBIS 18%", 1, [("On Net Total", "210301", 18, None, 0, "ITBIS 18%")]),
	("ITBIS 16%", 0, [("On Net Total", "210301", 16, None, 0, "ITBIS 16%")]),
	(
		"ITBIS 18% y Propina Legal 10%",
		0,
		[
			("On Net Total", "210301", 18, None, 0, "ITBIS 18%"),
			("On Net Total", "210407", 10, None, 0, "Propina legal 10%"),
		],
	),
]

PLANTILLAS_COMPRA = [
	("ITBIS 18% Compras", 1, [("On Net Total", "110501", 18, None, 0, "ITBIS 18%")]),
	("ITBIS 16% Compras", 0, [("On Net Total", "110501", 16, None, 0, "ITBIS 16%")]),
	(
		"Servicios de Persona Jurídica - Retención 30% del ITBIS",
		0,
		[
			("On Net Total", "110501", 18, None, 0, "ITBIS 18%"),
			("On Previous Row Amount", "210302", 30, 1, 1, "Retención 30% del ITBIS"),
		],
	),
	# Tasas de ISR del art. 309 del Código Tributario, modificado por la Ley 30-26 (vigentes desde el
	# 1/7/2026): 15% a honorarios, comisiones y alquileres de personas físicas; servicios técnicos de
	# personas físicas: 15% sobre una renta presunta del 20% (3% efectivo). Antes eran 10% y 2%.
	(
		"Servicios de Persona Física - Retención 100% ITBIS y 15% ISR",
		0,
		[
			("On Net Total", "110501", 18, None, 0, "ITBIS 18%"),
			("On Previous Row Amount", "210302", 100, 1, 1, "Retención 100% del ITBIS"),
			("On Net Total", "210303", 15, None, 1, "Retención ISR 15%"),
		],
	),
	(
		"Servicios Técnicos de Persona Física - Retención 100% ITBIS y 3% ISR",
		0,
		[
			("On Net Total", "110501", 18, None, 0, "ITBIS 18%"),
			("On Previous Row Amount", "210302", 100, 1, 1, "Retención 100% del ITBIS"),
			("On Net Total", "210303", 3, None, 1, "Retención ISR 3% (15% sobre renta presunta del 20%)"),
		],
	),
	(
		"Retención ISR 15% (sin ITBIS)",
		0,
		[("On Net Total", "210303", 15, None, 1, "Retención ISR 15%")],
	),
]

# Plantillas creadas por versiones anteriores de la app con tasas derogadas: título viejo -> nuevo
PLANTILLAS_RENOMBRADAS = {
	"Servicios de Persona Física - Retención 100% ITBIS y 10% ISR": (
		"Servicios de Persona Física - Retención 100% ITBIS y 15% ISR"
	),
	"Retención ISR 10% (sin ITBIS)": "Retención ISR 15% (sin ITBIS)",
}

# Documentos que indican que la empresa ya tiene operaciones: con ellos no se reemplaza el catálogo
DOCTYPES_MOVIMIENTOS = [
	"GL Entry",
	"Stock Ledger Entry",
	"Payment Ledger Entry",
	"Sales Invoice",
	"POS Invoice",
	"Purchase Invoice",
	"Journal Entry",
	"Payment Entry",
	"Stock Entry",
	"Purchase Receipt",
	"Delivery Note",
]


# ---------------------------------------------------------------------------
# Construcción del árbol
# ---------------------------------------------------------------------------


def _padre(numero: str, numeros: set[str]) -> str | None:
	for largo in range(len(numero) - 1, 0, -1):
		if numero[:largo] in numeros:
			return numero[:largo]
	return None


def arbol() -> dict:
	"""Árbol en el formato que espera `create_charts(custom_chart=...)` de ERPNext."""
	numeros = {c[0] for c in CUENTAS}
	con_hijos = {_padre(c[0], numeros) for c in CUENTAS}
	nodos: dict[str, dict] = {}
	raiz: dict = {}

	for numero, nombre, account_type, categoria, _datos in CUENTAS:
		nodo = {"account_number": numero}
		if account_type:
			nodo["account_type"] = account_type
		if categoria:
			nodo["account_category"] = categoria
		if numero in con_hijos:
			nodo["is_group"] = 1

		padre = _padre(numero, numeros)
		if padre:
			nodos[padre][nombre] = nodo
		else:
			nodo["root_type"] = ROOT_TYPE[numero[0]]
			raiz[nombre] = nodo
		nodos[numero] = nodo

	return raiz


def datos_dgii() -> dict[str, dict]:
	"""Datos DGII por número de cuenta, con la herencia de grupo a subcuentas ya resuelta."""
	numeros = {c[0] for c in CUENTAS}
	resultado: dict[str, dict] = {}
	for numero, _nombre, _tipo, _cat, datos in CUENTAS:
		padre = _padre(numero, numeros)
		resultado[numero] = {**(resultado.get(padre) or {}), **datos} if padre else dict(datos)
	return resultado


# ---------------------------------------------------------------------------
# Aplicación a una empresa
# ---------------------------------------------------------------------------


def es_empresa_rd(company: str) -> bool:
	return frappe.db.get_value("Company", company, "country") == PAIS


def tiene_movimientos(company: str) -> bool:
	return any(frappe.db.exists(dt, {"company": company}) for dt in DOCTYPES_MOVIMIENTOS)


def aplicar_automaticamente() -> bool:
	valor = frappe.db.get_single_value("Configuracion DGII", "aplicar_catalogo_cuentas")
	return valor is None or cint(valor) == 1


def aplicar_catalogo_dgii(company: str) -> bool:
	"""Reemplaza el catálogo de cuentas de la empresa por el catálogo DGII.

	Solo actúa en empresas de República Dominicana sin movimientos. Devuelve True si lo aplicó.
	"""
	if not es_empresa_rd(company):
		return False
	if tiene_movimientos(company):
		frappe.log_error(
			title=_("Catálogo DGII no aplicado"),
			message=_(
				"La empresa {0} ya tiene movimientos; su catálogo de cuentas no se reemplazó automáticamente."
			).format(company),
		)
		return False

	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		unset_existing_data,
	)

	anteriores = frappe.get_all("Account", filters={"company": company}, pluck="name")
	unset_existing_data(company)
	_limpiar_referencias(company, anteriores)

	frappe.local.flags.ignore_root_company_validation = True
	create_charts(company, custom_chart=arbol())

	cuentas = _cuentas_por_numero(company)
	_marcar_datos_dgii(cuentas)
	estados_ir2.asignar_casillas(company)
	_asignar_cuentas_por_defecto(company, cuentas)
	_crear_plantillas_impuestos(company, cuentas)

	frappe.db.set_value("Company", company, "rd_catalogo_dgii", 1, update_modified=False)
	frappe.clear_cache()
	return True


def _cuentas_por_numero(company: str) -> dict[str, str]:
	return {
		d.account_number: d.name
		for d in frappe.get_all("Account", filters={"company": company}, fields=["name", "account_number"])
		if d.account_number
	}


def _limpiar_referencias(company: str, cuentas: list[str]):
	"""Quita los enlaces a las cuentas borradas (almacenes, categorías de activo, tipos de gasto, ...).

	En tablas hijas por empresa donde la cuenta es obligatoria se borra la fila; en lo demás se
	deja el campo vacío. Solo toca valores que eran cuentas de esta empresa.
	"""
	if not cuentas:
		return

	campos = frappe.get_all(
		"DocField",
		filters={"fieldtype": "Link", "options": "Account", "parenttype": "DocType"},
		fields=["parent", "fieldname"],
	) + frappe.get_all(
		"Custom Field",
		filters={"fieldtype": "Link", "options": "Account"},
		fields=["dt as parent", "fieldname"],
	)
	nombres = tuple(cuentas)

	for campo in campos:
		if campo.parent in ("Account", "Company"):
			continue
		meta = frappe.get_meta(campo.parent)
		if meta.issingle or meta.is_virtual or not frappe.db.table_exists(campo.parent):
			continue
		if not frappe.db.has_column(campo.parent, campo.fieldname):
			continue

		df = meta.get_field(campo.fieldname)
		if meta.istable and df and df.reqd and meta.has_field("company"):
			frappe.db.delete(campo.parent, {campo.fieldname: ("in", nombres), "company": company})
		else:
			tabla = frappe.qb.DocType(campo.parent)
			columna = tabla[campo.fieldname]
			frappe.qb.update(tabla).set(columna, None).where(columna.isin(nombres)).run()


def _marcar_datos_dgii(cuentas: dict[str, str]):
	for numero, datos in datos_dgii().items():
		if not datos or numero not in cuentas:
			continue
		valores = {}
		if datos.get("concepto"):
			valores["rd_concepto_fiscal"] = datos["concepto"]
		if datos.get("tbs"):
			valores["rd_tipo_bienes_servicios"] = datos["tbs"]
		if datos.get("ing"):
			valores["rd_tipo_ingreso"] = datos["ing"]
		frappe.db.set_value("Account", cuentas[numero], valores, update_modified=False)


def _asignar_cuentas_por_defecto(company: str, cuentas: dict[str, str]):
	meta = frappe.get_meta("Company")
	valores = {
		campo: cuentas[numero]
		for campo, numero in CUENTAS_POR_DEFECTO.items()
		if meta.has_field(campo) and numero in cuentas
	}
	frappe.db.set_value("Company", company, valores, update_modified=False)

	doc = frappe.get_doc("Company", company)
	doc.set_mode_of_payment_account()

	# Frappe HR: cuenta de gasto de los tipos de reclamo de gastos (si no, HR crea "Expense Claims")
	if hrms_instalado() and CUENTA_RECLAMOS_GASTOS in cuentas:
		frappe.db.delete("Expense Claim Account", {"company": company, "default_account": ("is", "not set")})
		for tipo in frappe.get_all("Expense Claim Type", pluck="name"):
			if frappe.db.exists("Expense Claim Account", {"parent": tipo, "company": company}):
				continue
			tipo_doc = frappe.get_doc("Expense Claim Type", tipo)
			tipo_doc.append(
				"accounts", {"company": company, "default_account": cuentas[CUENTA_RECLAMOS_GASTOS]}
			)
			tipo_doc.save(ignore_permissions=True)


def _crear_plantillas_impuestos(company: str, cuentas: dict[str, str]):
	centro_costo = frappe.get_cached_value("Company", company, "cost_center")

	for doctype, plantillas in (
		("Sales Taxes and Charges Template", PLANTILLAS_VENTA),
		("Purchase Taxes and Charges Template", PLANTILLAS_COMPRA),
	):
		for titulo, por_defecto, filas in plantillas:
			if frappe.db.exists(doctype, {"title": titulo, "company": company}):
				continue
			taxes = []
			for tipo_cargo, numero, tasa, fila_base, deducir, descripcion in filas:
				fila = {
					"charge_type": tipo_cargo,
					"account_head": cuentas[numero],
					"rate": tasa,
					"description": descripcion,
					"cost_center": centro_costo,
				}
				if fila_base:
					fila["row_id"] = str(fila_base)
				if doctype == "Purchase Taxes and Charges Template":
					fila["category"] = "Total"
					fila["add_deduct_tax"] = "Deduct" if deducir else "Add"
				taxes.append(fila)

			frappe.get_doc(
				{
					"doctype": doctype,
					"title": titulo,
					"company": company,
					"is_default": por_defecto,
					"taxes": taxes,
				}
			).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def al_actualizar_empresa(doc, method=None):
	"""doc_events: Company -> on_update. Corre después de que ERPNext crea el catálogo estándar."""
	if frappe.local.flags.ignore_chart_of_accounts or frappe.flags.in_install:
		return
	if doc.country != PAIS or cint(doc.get("rd_catalogo_dgii")) or not aplicar_automaticamente():
		return
	if aplicar_catalogo_dgii(doc.name):
		frappe.msgprint(
			_("Se aplicó el catálogo de cuentas DGII ({0}) a la empresa {1}.").format(
				NOMBRE_CATALOGO, doc.name
			),
			alert=True,
			indicator="green",
		)


def aplicar_a_empresas_rd():
	"""after_install / after_migrate: aplica el catálogo a las empresas RD que aún no lo tienen."""
	if not aplicar_automaticamente():
		return
	for company in frappe.get_all("Company", filters={"country": PAIS, "rd_catalogo_dgii": 0}, pluck="name"):
		if aplicar_catalogo_dgii(company):
			print(f"erpnext_rd: catálogo de cuentas DGII aplicado a {company}")
		else:
			print(f"erpnext_rd: {company} tiene movimientos; no se reemplazó su catálogo de cuentas")
