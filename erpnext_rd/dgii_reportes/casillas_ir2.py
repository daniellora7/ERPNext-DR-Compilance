"""Casillas de los anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2, y la casilla
de cada cuenta del catálogo DGII. El cálculo de los anexos está en `estados_ir2.py`."""

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


# Casilla de cada cuenta del catálogo DGII (cuentas_dgii.CUENTAS), por número. Las subcuentas que
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
