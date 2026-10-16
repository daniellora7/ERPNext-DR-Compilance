"""Anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2 desde la contabilidad.

Cada cuenta lleva su casilla del IR-2 (`Account.rd_casilla_ir2`). Las del catálogo DGII la traen
asignada por número de cuenta (`CASILLAS_CATALOGO`); una cuenta sin casilla toma la de su cuenta
padre más cercana y, si ninguna la tiene, la de su tipo (`casilla_por_tipo`), con un aviso.

- A-1: saldos al cierre. Activos con saldo deudor; depreciación acumulada y provisiones (5.x) como
  deducción; pasivos y patrimonio con saldo acreedor. El resultado de los ejercicios anteriores sin
  asiento de cierre va a 10.4 y el del ejercicio a 10.5 (el asiento de cierre del período no se
  toma en cuenta, así el balance cuadra con o sin él).
- B-1: movimiento del ejercicio sin el asiento de cierre. Ingresos con saldo acreedor; devoluciones
  y descuentos (1.3 y 1.4) se restan; costos y gastos con saldo deudor. La depreciación de las cuentas
  de la casilla 9 se reparte entre 9.1, 9.2 y 9.3 según la categoría fiscal de cada activo. El
  impuesto sobre la renta del ejercicio no entra (la casilla 14 es el beneficio antes del ISR).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

A1 = "A-1"
B1 = "B-1"
EXCLUIDO = "No va en el IR-2 (ISR del ejercicio)"

# (código, descripción, casillas [(código, descripción)])
GRUPOS_A1 = [
	(
		"1",
		"Activos corrientes",
		[
			("1.1", "Cajas y bancos"),
			("1.2", "Cuentas por cobrar a clientes"),
			("1.3", "Cuentas por cobrar a relacionados"),
			("1.4", "Otras cuentas por cobrar"),
			("1.5", "Inventario de mercancías o productos terminados"),
			("1.6", "Inventario de materia prima"),
			("1.7", "Inventario de productos en proceso"),
			("1.8", "Otros inventarios"),
			("1.9", "Mercancías en tránsito"),
			("1.10", "Gastos pagados por adelantado"),
			("1.11", "Otros activos corrientes"),
			("1.12", "Dividendos a cuenta entregados en el ejercicio"),
		],
	),
	(
		"2",
		"Activos fijos",
		[
			("2.1", "Edificaciones (categoría 1)"),
			("2.2", "Edificaciones de explotaciones agropecuarias (categoría 1)"),
			("2.3", "Automóviles y equipos (categoría 2)"),
			("2.4", "Otros activos fijos depreciables (categoría 3)"),
			("2.5", "Activos fijos no depreciables (incluye terrenos urbanos)"),
			("2.6", "Activos fijos no depreciables (incluye terrenos rurales)"),
			("2.7", "Revaluación de activos"),
		],
	),
	("3", "Inversiones", [("3.1", "Depósitos"), ("3.2", "Acciones"), ("3.3", "Otras inversiones")]),
	(
		"4",
		"Otros activos",
		[
			("4.1", "Otros activos no amortizables"),
			("4.2", "Impuesto sobre la renta diferido o anticipado"),
			("4.3", "Otros activos amortizables"),
		],
	),
	(
		"5",
		"Depreciación acumulada y provisiones (-)",
		[
			("5.1", "Depreciación acumulada (categoría 1)"),
			("5.2", "Depreciación acumulada edificaciones agropecuarias"),
			("5.3", "Depreciación acumulada (categoría 2)"),
			("5.4", "Depreciación acumulada (categoría 3)"),
			("5.5", "Provisión para cuentas incobrables"),
			("5.6", "Provisión de inventario"),
			("5.7", "Otras provisiones"),
		],
	),
	(
		"7",
		"Acreedores a corto plazo",
		[
			("7.1", "Préstamos"),
			("7.2", "Cuentas por pagar"),
			("7.3", "Impuestos por pagar"),
			("7.4", "Otras cuentas por pagar"),
			("7.5", "Cobros anticipados"),
			("7.6", "Aportes para futura capitalización"),
		],
	),
	(
		"8",
		"Acreedores a largo plazo",
		[
			("8.1", "Préstamos hipotecarios"),
			("8.2", "Préstamos con instituciones financieras locales"),
			("8.3", "Préstamos con instituciones financieras del exterior"),
			("8.4", "Préstamos con entidades relacionadas locales"),
			("8.5", "Préstamos con entidades relacionadas del exterior"),
			("8.6", "Préstamos con entidades acogidas a regímenes especiales"),
			("8.7", "Préstamos con organismos internacionales"),
			("8.8", "Préstamos con accionistas"),
		],
	),
	("9", "Otros pasivos", [("9", "Otros pasivos")]),
	(
		"10",
		"Patrimonio",
		[
			("10.1", "Capital suscrito y pagado"),
			("10.2", "Reserva legal"),
			("10.3", "Superávit por revaluación de activos"),
			("10.4", "Beneficios (pérdidas) de ejercicios anteriores"),
			("10.5", "Beneficio (pérdida) del ejercicio actual"),
			("10.6", "Otras reservas"),
		],
	),
]

GRUPOS_B1 = [
	(
		"1",
		"Ingresos de operaciones netos",
		[
			("1.1", "Ingresos ventas locales"),
			("1.2", "Ingresos exportaciones"),
			("1.3", "Devoluciones sobre ventas (-)"),
			("1.4", "Descuentos sobre ventas (-)"),
			("1.5", "Otros ingresos"),
		],
	),
	(
		"2",
		"Ingresos financieros",
		[
			("2.1", "Intereses por inversiones en instituciones financieras"),
			("2.2", "Intereses por inversiones en instituciones no financieras"),
			("2.3", "Por dividendos"),
			("2.4", "Intereses por préstamos con entidades relacionadas"),
			("2.5", "Intereses por préstamos con entidades no relacionadas"),
			("2.6", "Otros ingresos financieros"),
		],
	),
	(
		"3",
		"Ingresos extraordinarios",
		[
			("3.1", "Por ventas de activos depreciables"),
			("3.2", "Por ventas de bienes de capital"),
			("3.3", "Diferencias positivas cambiarias"),
			("3.4", "Ingresos correspondientes a otros ejercicios"),
			("3.5", "Otros ingresos extraordinarios"),
		],
	),
	("5", "Costo de venta", [("5", "Costo de venta")]),
	(
		"6",
		"Gastos de personal",
		[
			("6.1", "Sueldos y salarios"),
			("6.2", "Retribuciones complementarias"),
			("6.3", "Seguros"),
			("6.4", "Aportaciones a la seguridad social"),
			("6.5", "Aporte INFOTEP"),
			("6.6", "Otros gastos de personal"),
			("6.7", "ITBIS pagado en proporcionalidad"),
		],
	),
	(
		"7",
		"Gastos por trabajos, suministros y servicios",
		[
			("7.1", "Honorarios profesionales (personas físicas)"),
			("7.2", "Honorarios profesionales (personas morales)"),
			("7.3", "Honorarios por servicios del exterior (Ley 392-07)"),
			("7.4", "Honorarios por servicios del exterior"),
			("7.5", "Seguridad, mensajería, transportes y servicios (personas físicas)"),
			("7.6", "Seguridad, mensajería, transportes y servicios (personas morales)"),
			("7.7", "Otros gastos por trabajos, suministros y servicios"),
			("7.8", "ITBIS pagado en proporcionalidad"),
		],
	),
	(
		"8",
		"Arrendamientos",
		[
			("8.1", "De inmuebles (a personas físicas)"),
			("8.2", "De inmuebles (a personas morales)"),
			("8.3", "Otros arrendamientos"),
			("8.4", "ITBIS pagado en proporcionalidad"),
		],
	),
	(
		"9",
		"Gastos de activos fijos",
		[
			("9.1", "Depreciación de activos fijos (categoría 1)"),
			("9.2", "Depreciación de activos fijos (categoría 2)"),
			("9.3", "Depreciación de activos fijos (categoría 3)"),
			("9.4", "Reparaciones de activos fijos (categoría 1)"),
			("9.5", "Reparaciones de activos fijos (categorías 2 y 3)"),
			("9.6", "Mantenimiento de los activos fijos"),
			("9.7", "Amortización de bienes intangibles"),
			("9.8", "Amortización de mejoras en propiedades arrendadas"),
			("9.9", "ITBIS pagado en proporcionalidad"),
		],
	),
	(
		"10",
		"Gastos de representación",
		[
			("10.1", "Relaciones públicas"),
			("10.2", "Publicidad"),
			("10.3", "Viajes"),
			("10.4", "Donaciones"),
			("10.5", "Donaciones a Proindustria (Ley 392-07)"),
			("10.6", "Otros gastos de representación"),
			("10.7", "Promociones"),
			("10.8", "ITBIS pagado en proporcionalidad"),
		],
	),
	("11", "Otras deducciones admitidas", [("11", "Otras deducciones admitidas")]),
	(
		"12",
		"Gastos financieros",
		[
			("12.1", "Por préstamos con instituciones financieras locales"),
			("12.2", "Por préstamos con entidades del exterior"),
			("12.3", "Por préstamos con entidades relacionadas locales"),
			("12.4", "Por préstamos con entidades relacionadas del exterior"),
			("12.5", "Por préstamos con personas físicas"),
			("12.6", "Por préstamos con personas físicas relacionadas locales"),
			("12.7", "Por préstamos con personas físicas relacionadas en el exterior"),
			("12.8", "Por el impuesto a la emisión de cheques y pagos por transferencia"),
			("12.9", "Por préstamos con entidades acogidas a regímenes especiales"),
			("12.10", "Otros gastos financieros"),
		],
	),
	(
		"13",
		"Gastos extraordinarios",
		[
			("13.1", "Por pérdidas en ventas de activos depreciables"),
			("13.2", "Por pérdidas en ventas de bienes de capital"),
			("13.3", "Pérdidas por cuentas incobrables"),
			("13.4", "Provisión cuentas incobrables"),
			("13.5", "Por diferencias negativas cambiarias"),
			("13.6", "Otros gastos extraordinarios"),
			("13.7", "Provisión de inventario"),
			("13.8", "Otras provisiones"),
		],
	),
]
INGRESOS_B1 = ("1", "2", "3")
RESTAN_B1 = ("1.3", "1.4")
DEPRECIACION_B1 = {"Categoría 1": "9.1", "Categoría 2": "9.2", "Categoría 3": "9.3"}


def casilla(anexo: str, codigo: str) -> str:
	"""Valor del campo `rd_casilla_ir2`: «B-1 6.1 Sueldos y salarios»."""
	grupos = GRUPOS_A1 if anexo == A1 else GRUPOS_B1
	for _g, _d, casillas in grupos:
		for c, descripcion in casillas:
			if c == codigo:
				return f"{anexo} {c} {descripcion}"
	raise KeyError(f"{anexo} {codigo}")


def opciones() -> list[str]:
	return [
		f"{anexo} {c} {d}"
		for anexo, grupos in ((A1, GRUPOS_A1), (B1, GRUPOS_B1))
		for _g, _gd, casillas in grupos
		for c, d in casillas
	] + [EXCLUIDO]


def codigo(valor: str | None) -> tuple[str, str] | None:
	"""(anexo, código) de un valor de `rd_casilla_ir2`."""
	if not valor or valor == EXCLUIDO:
		return None
	anexo, cod, _resto = valor.split(" ", 2)
	return anexo, cod


def _a(cod):
	return casilla(A1, cod)


def _b(cod):
	return casilla(B1, cod)


# Casilla de cada cuenta del catálogo DGII (catalogo_cuentas.CUENTAS), por número. Las subcuentas que
# no aparecen toman la de su grupo.
CASILLAS_CATALOGO = {
	"1101": _a("1.1"),
	"1102": _a("1.1"),
	"110301": _a("1.2"),
	"110302": _a("1.2"),
	"110303": _a("1.4"),
	"110304": _a("1.3"),
	"110305": _a("1.4"),
	"110306": _a("5.5"),
	"110307": _a("1.4"),
	"110401": _a("1.6"),
	"110402": _a("1.7"),
	"110403": _a("1.5"),
	"110404": _a("1.5"),
	"110405": _a("1.8"),
	"110406": _a("1.9"),
	"1105": _a("1.11"),
	"1106": _a("1.10"),
	"1107": _a("3.1"),
	"120101": _a("2.5"),
	"120102": _a("2.1"),
	"120103": _a("2.3"),
	"120104": _a("2.3"),
	"120105": _a("2.3"),
	"120106": _a("2.4"),
	"120107": _a("2.4"),
	"120108": _a("4.3"),
	"120109": _a("4.1"),
	"120201": _a("5.1"),
	"120202": _a("5.3"),
	"120203": _a("5.4"),
	"120204": _a("4.3"),
	"1203": _a("4.3"),
	"120401": _a("4.1"),
	"120402": _a("3.3"),
	"120403": _a("4.2"),
	"13": _a("1.11"),
	"210101": _a("7.2"),
	"210102": _a("7.2"),
	"210103": _a("7.4"),
	"210104": _a("7.4"),
	"2102": _a("7.4"),
	"2103": _a("7.3"),
	"2104": _a("7.4"),
	"2105": _a("7.5"),
	"210601": _a("7.1"),
	"210602": _a("7.1"),
	"210603": _a("7.4"),
	"2107": _a("7.4"),
	"2201": _a("8.2"),
	"2202": _a("8.4"),
	"2203": _a("9"),
	"2204": _a("9"),
	"3101": _a("10.1"),
	"3102": _a("7.6"),
	"3201": _a("10.2"),
	"3202": _a("10.6"),
	"3301": _a("10.4"),
	"3302": _a("10.5"),
	"3303": _a("10.4"),
	"3304": _a("10.4"),
	"34": _a("10.3"),
	"4101": _b("1.1"),
	"4102": _b("1.1"),
	"4103": _b("1.2"),
	"4104": _b("1.3"),
	"4105": _b("1.4"),
	"4201": _b("2.1"),
	"4202": _b("2.6"),
	"43": _b("3.5"),
	"44": _b("1.5"),
	"45": _b("3.1"),
	"46": _b("1.5"),
	"5": _b("5"),
	"6101": _b("6.1"),
	"6102": _b("6.1"),
	"6103": _b("6.1"),
	"6104": _b("6.1"),
	"6105": _b("6.1"),
	"6106": _b("6.1"),
	"6107": _b("6.1"),
	"6108": _b("6.4"),
	"6109": _b("6.5"),
	"6110": _b("6.3"),
	"6111": _b("6.6"),
	"6112": _b("6.6"),
	"6113": _b("6.6"),
	"6201": _b("7.2"),
	"62": _b("7.7"),
	"6209": _b("7.6"),
	"6210": _b("7.6"),
	"6211": _b("7.6"),
	"6301": _b("8.2"),
	"6302": _b("8.3"),
	"6303": _b("8.3"),
	"6401": _b("9.3"),
	"6402": _b("9.7"),
	"6403": _b("9.5"),
	"6404": _b("9.6"),
	"6501": _b("10.1"),
	"6502": _b("10.2"),
	"6503": _b("10.6"),
	"6504": _b("10.3"),
	"6505": _b("10.6"),
	"66": _b("11"),
	"6602": _b("10.4"),
	"6603": _b("13.3"),
	"6701": _b("12.1"),
	"6702": _b("12.10"),
	"6703": _b("12.8"),
	"6704": _b("13.5"),
	"6705": _b("13.5"),
	"68": _b("13.6"),
	"6804": EXCLUIDO,
	"69": _b("7.7"),
}


def casilla_por_tipo(root_type: str, account_type: str | None) -> str:
	"""Casilla de una cuenta sin casilla propia ni en sus padres."""
	if root_type == "Asset":
		return _a(
			{
				"Cash": "1.1",
				"Bank": "1.1",
				"Receivable": "1.2",
				"Stock": "1.5",
				"Fixed Asset": "2.4",
				"Capital Work in Progress": "4.1",
				"Accumulated Depreciation": "5.4",
			}.get(account_type, "1.11")
		)
	if root_type == "Liability":
		return _a({"Payable": "7.2", "Tax": "7.3"}.get(account_type, "7.4"))
	if root_type == "Equity":
		return _a("10.6")
	if root_type == "Income":
		return _b("1.5")
	return _b({"Cost of Goods Sold": "5", "Depreciation": "9.3"}.get(account_type, "11"))


def asignar_casillas(company: str | None = None):
	"""Pone la casilla del catálogo DGII a las cuentas que aún no tienen (por número de cuenta), en
	`company` o en las empresas con el catálogo DGII aplicado."""
	empresas = (
		[company] if company else frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name")
	)
	if not empresas:
		return
	filtros = {
		"company": ("in", empresas),
		"rd_casilla_ir2": ("is", "not set"),
		"account_number": ("in", list(CASILLAS_CATALOGO)),
	}
	for cuenta in frappe.get_all("Account", filters=filtros, fields=["name", "account_number"]):
		frappe.db.set_value(
			"Account",
			cuenta.name,
			"rd_casilla_ir2",
			CASILLAS_CATALOGO[cuenta.account_number],
			update_modified=False,
		)


def casillas_de_cuentas(company: str) -> tuple[dict[str, str | None], list[str]]:
	"""Casilla efectiva de cada cuenta hoja (propia, del padre más cercano o por tipo) y las cuentas
	clasificadas por tipo."""
	cuentas = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=["name", "lft", "rgt", "is_group", "root_type", "account_type", "rd_casilla_ir2"],
		order_by="lft",
	)
	grupos = [c for c in cuentas if c.is_group and c.rd_casilla_ir2]
	resultado, por_tipo = {}, []
	for c in cuentas:
		if c.is_group:
			continue
		valor = c.rd_casilla_ir2
		if not valor:
			# El padre más cercano con casilla: el de lft mayor que contiene a la cuenta
			padres = [g for g in grupos if g.lft < c.lft and g.rgt > c.rgt]
			valor = padres[-1].rd_casilla_ir2 if padres else None
		if not valor:
			valor = casilla_por_tipo(c.root_type, c.account_type)
			por_tipo.append(c.name)
		resultado[c.name] = valor
	return resultado, por_tipo


def _saldos(company: str, condicion: str, valores: dict) -> dict[str, float]:
	"""Saldo deudor (débito - crédito) por cuenta, sin el asiento de cierre del período."""
	return {
		cuenta: flt(saldo)
		for cuenta, saldo in frappe.db.sql(
			f"""SELECT account, SUM(debit - credit) FROM `tabGL Entry`
			WHERE company = %(company)s AND is_cancelled = 0
				AND voucher_type != 'Period Closing Voucher' AND {condicion}
			GROUP BY account""",
			{"company": company, **valores},
		)
	}


def _depreciacion_por_categoria(company: str, desde, hasta) -> dict[str, float]:
	from erpnext_rd.dgii_reportes import ir2

	total = {}
	categorias = dict(
		frappe.get_all("Asset", filters={"company": company}, fields=["name", "asset_category"], as_list=True)
	)
	for asset, monto in ir2.depreciacion_contable(company, desde, hasta).items():
		categoria = ir2.categoria_fiscal(categorias[asset]) if categorias.get(asset) else None
		cod = DEPRECIACION_B1.get(categoria, "9.3")
		total[cod] = total.get(cod, 0) + monto
	return total


def calcular(company: str, desde, hasta) -> frappe._dict:
	"""Montos por casilla de los anexos A-1 y B-1, sus totales y avisos."""
	desde, hasta = getdate(desde), getdate(hasta)
	casillas, por_tipo = casillas_de_cuentas(company)
	raices = dict(
		frappe.get_all("Account", filters={"company": company}, fields=["name", "root_type"], as_list=True)
	)
	cuentas_por_casilla: dict[tuple, list[str]] = {}

	# B-1: movimiento del ejercicio
	b1: dict[str, float] = {}
	isr = 0.0
	for cuenta, saldo in _saldos(
		company, "posting_date BETWEEN %(desde)s AND %(hasta)s", {"desde": desde, "hasta": hasta}
	).items():
		if raices.get(cuenta) not in ("Income", "Expense"):
			continue
		valor = casillas.get(cuenta)
		if valor == EXCLUIDO:
			isr += saldo
			continue
		par = codigo(valor)
		if not par or par[0] != B1:
			par = codigo(casilla_por_tipo(raices[cuenta], None))
		cod = par[1]
		# Ingresos con saldo acreedor; devoluciones, descuentos, costos y gastos con saldo deudor
		ingreso = cod.split(".")[0] in INGRESOS_B1 and cod not in RESTAN_B1
		b1[cod] = b1.get(cod, 0) + (-saldo if ingreso else saldo)
		cuentas_por_casilla.setdefault((B1, cod), []).append(cuenta)

	# La depreciación contable de la casilla 9.x, por categoría fiscal de los activos
	depreciacion = _depreciacion_por_categoria(company, desde, hasta)
	en_casillas = sum(b1.get(c, 0) for c in DEPRECIACION_B1.values())
	if depreciacion and en_casillas:
		reparto = sum(depreciacion.values())
		for c in DEPRECIACION_B1.values():
			b1.pop(c, None)
		for c, monto in depreciacion.items():
			b1[c] = b1.get(c, 0) + monto
		if flt(en_casillas - reparto, 2):
			b1["9.3"] = b1.get("9.3", 0) + en_casillas - reparto

	totales_b1 = {}
	for g, _d, cs in GRUPOS_B1:
		totales_b1[g] = flt(sum(-b1.get(c, 0) if c in RESTAN_B1 else b1.get(c, 0) for c, _x in cs), 2)
	ingresos = flt(sum(totales_b1[g] for g in INGRESOS_B1), 2)
	costos = flt(sum(v for g, v in totales_b1.items() if g not in INGRESOS_B1), 2)
	totales_b1["4"] = ingresos
	totales_b1["14"] = flt(ingresos - costos, 2)

	# A-1: saldos al cierre
	a1: dict[str, float] = {}
	resultado_anterior = 0.0
	resultado_ejercicio = 0.0
	for cuenta, saldo in _saldos(company, "posting_date <= %(hasta)s", {"hasta": hasta}).items():
		raiz = raices.get(cuenta)
		if raiz in ("Income", "Expense"):
			continue
		valor = casillas.get(cuenta)
		par = codigo(valor) if valor else None
		if not par or par[0] != A1:
			par = (A1, codigo(casilla_por_tipo(raiz, None))[1])
		cod = par[1]
		grupo = cod.split(".")[0]
		if grupo in ("1", "2", "3", "4"):
			monto = saldo
		else:  # 5 (deducciones del activo), pasivos y patrimonio: saldo acreedor
			monto = -saldo
		a1[cod] = a1.get(cod, 0) + monto
		cuentas_por_casilla.setdefault((A1, cod), []).append(cuenta)

	for cuenta, saldo in _saldos(company, "posting_date < %(desde)s", {"desde": desde}).items():
		if raices.get(cuenta) in ("Income", "Expense"):
			resultado_anterior -= saldo
	for cuenta, saldo in _saldos(
		company, "posting_date BETWEEN %(desde)s AND %(hasta)s", {"desde": desde, "hasta": hasta}
	).items():
		if raices.get(cuenta) in ("Income", "Expense"):
			resultado_ejercicio -= saldo
	a1["10.4"] = a1.get("10.4", 0) + resultado_anterior
	a1["10.5"] = a1.get("10.5", 0) + resultado_ejercicio

	totales_a1 = {g: flt(sum(a1.get(c, 0) for c, _x in cs), 2) for g, _d, cs in GRUPOS_A1}
	totales_a1["6"] = flt(
		totales_a1["1"] + totales_a1["2"] + totales_a1["3"] + totales_a1["4"] - totales_a1["5"], 2
	)
	totales_a1["11"] = flt(totales_a1["7"] + totales_a1["8"] + totales_a1["9"] + totales_a1["10"], 2)

	avisos = []
	if por_tipo:
		avisos.append(
			_("Cuentas sin casilla del IR-2, clasificadas por su tipo: {0}").format(", ".join(por_tipo[:10]))
			+ ("…" if len(por_tipo) > 10 else "")
		)
	if flt(totales_a1["6"] - totales_a1["11"], 2):
		avisos.append(
			_("El balance no cuadra: activos {0}, pasivos y patrimonio {1}.").format(
				frappe.format(totales_a1["6"], "Currency"), frappe.format(totales_a1["11"], "Currency")
			)
		)
	return frappe._dict(
		a1={c: flt(v, 2) for c, v in a1.items()},
		b1={c: flt(v, 2) for c, v in b1.items()},
		totales_a1=totales_a1,
		totales_b1=totales_b1,
		isr=flt(isr, 2),
		cuentas=cuentas_por_casilla,
		avisos=avisos,
	)


def _filas(anexo: str, titulo: str, grupos, montos, totales, cuentas, extra) -> list[dict]:
	filas = [{"casilla": anexo, "descripcion": titulo, "negrita": 1}]
	for g, descripcion, casillas in grupos:
		filas.append(
			{"casilla": g, "descripcion": descripcion, "monto": totales[g], "negrita": 1, "indent": 0}
		)
		if len(casillas) == 1 and casillas[0][0] == g:
			filas[-1]["cuentas"] = ", ".join(cuentas.get((anexo, g), []))
			continue
		for c, d in casillas:
			filas.append(
				{
					"casilla": c,
					"descripcion": d,
					"monto": montos.get(c, 0),
					"cuentas": ", ".join(cuentas.get((anexo, c), [])),
					"indent": 1,
				}
			)
		filas.extend(extra.get(g, []))
	return filas


def reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "casilla", "label": _("Casilla"), "fieldtype": "Data", "width": 80},
		{"fieldname": "descripcion", "label": _("Descripción"), "fieldtype": "Data", "width": 420},
		{"fieldname": "monto", "label": _("Monto"), "fieldtype": "Currency", "width": 170},
		{"fieldname": "cuentas", "label": _("Cuentas"), "fieldtype": "Data", "width": 420},
	]
	if not (filters.company and filters.desde and filters.hasta):
		return columnas, []
	r = calcular(filters.company, filters.desde, filters.hasta)
	total_activos = {
		"casilla": "6",
		"descripcion": _("Total activos"),
		"monto": r.totales_a1["6"],
		"negrita": 1,
	}
	filas = _filas(
		A1,
		_("Anexo A-1: balance general al cierre"),
		GRUPOS_A1,
		r.a1,
		r.totales_a1,
		r.cuentas,
		{"5": [total_activos]},
	)
	filas.append(
		{
			"casilla": "11",
			"descripcion": _("Total pasivos y patrimonio"),
			"monto": r.totales_a1["11"],
			"negrita": 1,
		}
	)
	filas.append({})
	total_ingresos = {
		"casilla": "4",
		"descripcion": _("Total ingresos"),
		"monto": r.totales_b1["4"],
		"negrita": 1,
	}
	filas += _filas(
		B1,
		_("Anexo B-1: estado de resultados del ejercicio"),
		GRUPOS_B1,
		r.b1,
		r.totales_b1,
		r.cuentas,
		{"3": [total_ingresos]},
	)
	filas.append(
		{
			"casilla": "14",
			"descripcion": _("Beneficio (pérdida) antes del impuesto sobre la renta"),
			"monto": r.totales_b1["14"],
			"negrita": 1,
		}
	)
	resumen = [
		{
			"label": _("Total activos"),
			"value": r.totales_a1["6"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Pasivos y patrimonio"),
			"value": r.totales_a1["11"],
			"datatype": "Currency",
			"indicator": "Blue" if not flt(r.totales_a1["6"] - r.totales_a1["11"], 2) else "Red",
		},
		{
			"label": _("Beneficio antes del ISR"),
			"value": r.totales_b1["14"],
			"datatype": "Currency",
			"indicator": "Green" if r.totales_b1["14"] >= 0 else "Red",
		},
	]
	mensaje = " ".join(
		[
			_(
				"Saldos por casilla de los anexos A-1 y B-1 del IR-2, según la casilla de cada cuenta "
				"(campo «Casilla del IR-2» del catálogo de cuentas). Sin el asiento de cierre del período."
			),
			*r.avisos,
		]
	)
	return columnas, filas, mensaje, None, resumen
