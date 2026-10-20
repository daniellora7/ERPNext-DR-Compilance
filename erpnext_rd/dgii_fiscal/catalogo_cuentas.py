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

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_reportes import estados_ir2
from erpnext_rd.nomina_rd import hrms_instalado

PAIS = "Dominican Republic"
NOMBRE_CATALOGO = "República Dominicana - DGII"


def _tbs(codigo: int) -> str:
	return cat.TIPOS_BIENES_SERVICIOS[codigo - 1]


def _ing(codigo: int) -> str:
	return cat.TIPOS_INGRESO[codigo - 1]


# numero, nombre, account_type, account_category, datos DGII
# El padre de cada cuenta es la cuenta con el número más largo que sea prefijo del suyo.
# Los datos DGII de un grupo (tbs = tipo 606, ing = tipo 607) se heredan a sus subcuentas.
CUENTAS = [
	# ------------------------------------------------------------------ ACTIVOS
	("1", "ACTIVOS", "", "", {}),
	("11", "ACTIVOS CORRIENTES", "", "", {}),
	("1101", "Caja", "Cash", "Cash and Cash Equivalents", {}),
	("110101", "Caja General", "Cash", "Cash and Cash Equivalents", {}),
	("110102", "Caja Chica", "Cash", "Cash and Cash Equivalents", {}),
	("1102", "Bancos", "Bank", "Cash and Cash Equivalents", {}),
	("110201", "Banco Cuenta Corriente", "Bank", "Cash and Cash Equivalents", {}),
	("1103", "Cuentas por Cobrar", "", "", {}),
	("110301", "Clientes Locales", "Receivable", "Trade Receivables", {}),
	("110302", "Clientes del Exterior", "Receivable", "Trade Receivables", {}),
	("110303", "Anticipos a Empleados", "Receivable", "Other Receivables", {}),
	("110304", "Cuentas por Cobrar a Relacionadas", "Receivable", "Other Receivables", {}),
	("110305", "Otras Cuentas por Cobrar", "Receivable", "Other Receivables", {}),
	("110306", "Estimación para Cuentas Incobrables", "", "Trade Receivables", {}),
	("110307", "Anticipos a Proveedores", "Payable", "Other Current Assets", {}),
	("1104", "Inventarios", "Stock", "Stock Assets", {}),
	("110401", "Inventario de Materia Prima", "Stock", "Stock Assets", {}),
	("110402", "Inventario de Productos en Proceso", "Stock", "Stock Assets", {}),
	("110403", "Inventario de Productos Terminados", "Stock", "Stock Assets", {}),
	("110404", "Inventario de Mercancías para la Venta", "Stock", "Stock Assets", {}),
	("110405", "Inventario de Materiales y Suministros", "Stock", "Stock Assets", {}),
	("110406", "Mercancías en Tránsito", "Stock", "Stock Assets", {}),
	("1105", "Impuestos Pagados por Anticipado", "", "Other Current Assets", {}),
	("110501", "ITBIS Pagado en Compras", "Tax", "Other Current Assets", {"concepto": cat.ITBIS}),
	("110502", "Anticipos de ISR Pagados", "", "Other Current Assets", {}),
	(
		"110503",
		"ISR Retenido por Terceros",
		"Tax",
		"Other Current Assets",
		{"concepto": cat.ISR_RETENIDO_POR_TERCEROS},
	),
	(
		"110504",
		"ITBIS Retenido por Terceros",
		"Tax",
		"Other Current Assets",
		{"concepto": cat.ITBIS_RETENIDO_POR_TERCEROS},
	),
	("110505", "Saldo a Favor de ITBIS", "", "Other Current Assets", {}),
	("110506", "Saldo a Favor de ISR", "", "Other Current Assets", {}),
	("1106", "Gastos Pagados por Anticipado", "", "Other Current Assets", {}),
	("110601", "Seguros Pagados por Anticipado", "", "Other Current Assets", {}),
	("110602", "Alquileres Pagados por Anticipado", "", "Other Current Assets", {}),
	("110603", "Otros Gastos Pagados por Anticipado", "", "Other Current Assets", {}),
	("1107", "Inversiones a Corto Plazo", "", "Short-term Investments", {}),
	("110701", "Certificados Financieros", "", "Short-term Investments", {}),
	("12", "ACTIVOS NO CORRIENTES", "", "", {}),
	("1201", "Propiedad, Planta y Equipo", "", "Tangible Assets", {}),
	("120101", "Terrenos", "Fixed Asset", "Tangible Assets", {}),
	("120102", "Edificaciones (Categoría 1)", "Fixed Asset", "Tangible Assets", {}),
	("120103", "Vehículos (Categoría 2)", "Fixed Asset", "Tangible Assets", {}),
	("120104", "Mobiliario y Equipo de Oficina (Categoría 2)", "Fixed Asset", "Tangible Assets", {}),
	("120105", "Equipos de Cómputo (Categoría 2)", "Fixed Asset", "Tangible Assets", {}),
	("120106", "Maquinarias y Equipos Industriales (Categoría 3)", "Fixed Asset", "Tangible Assets", {}),
	("120107", "Otros Activos Depreciables (Categoría 3)", "Fixed Asset", "Tangible Assets", {}),
	("120108", "Mejoras en Propiedades Arrendadas", "Fixed Asset", "Tangible Assets", {}),
	("120109", "Construcciones en Proceso", "Capital Work in Progress", "Tangible Assets", {}),
	("1202", "Depreciación Acumulada", "", "Tangible Assets", {}),
	("120201", "Depreciación Acumulada Categoría 1", "Accumulated Depreciation", "Tangible Assets", {}),
	("120202", "Depreciación Acumulada Categoría 2", "Accumulated Depreciation", "Tangible Assets", {}),
	("120203", "Depreciación Acumulada Categoría 3", "Accumulated Depreciation", "Tangible Assets", {}),
	("120204", "Amortización Acumulada de Mejoras", "Accumulated Depreciation", "Tangible Assets", {}),
	("1203", "Activos Intangibles", "", "Intangible Assets", {}),
	("120301", "Software y Licencias", "Fixed Asset", "Intangible Assets", {}),
	("120302", "Amortización Acumulada de Intangibles", "Accumulated Depreciation", "Intangible Assets", {}),
	("1204", "Otros Activos", "", "Other Non-current Assets", {}),
	("120401", "Depósitos en Garantía", "", "Other Non-current Assets", {}),
	("120402", "Inversiones a Largo Plazo", "", "Long-term Investments", {}),
	("120403", "Impuesto sobre la Renta Diferido Activo", "", "Other Non-current Assets", {}),
	("13", "CUENTAS TRANSITORIAS", "", "", {}),
	("1301", "Cuenta Temporal de Apertura", "Temporary", "Other Current Assets", {}),
	# ------------------------------------------------------------------ PASIVOS
	("2", "PASIVOS", "", "", {}),
	("21", "PASIVOS CORRIENTES", "", "", {}),
	("2101", "Cuentas por Pagar", "", "Trade Payables", {}),
	("210101", "Proveedores Locales", "Payable", "Trade Payables", {}),
	("210102", "Proveedores del Exterior", "Payable", "Trade Payables", {}),
	("210103", "Cuentas por Pagar a Relacionadas", "Payable", "Other Payables", {}),
	("210104", "Otras Cuentas por Pagar", "Payable", "Other Payables", {}),
	("2102", "Acumulaciones por Pagar", "", "Other Current Liabilities", {}),
	(
		"210201",
		"Inventario Recibido No Facturado",
		"Stock Received But Not Billed",
		"Other Current Liabilities",
		{},
	),
	(
		"210202",
		"Activo Recibido No Facturado",
		"Asset Received But Not Billed",
		"Other Current Liabilities",
		{},
	),
	(
		"210203",
		"Servicio Recibido No Facturado",
		"Service Received But Not Billed",
		"Other Current Liabilities",
		{},
	),
	("210204", "Gastos Acumulados por Pagar", "", "Other Current Liabilities", {}),
	("210205", "Intereses por Pagar", "", "Other Current Liabilities", {}),
	("2103", "Impuestos por Pagar", "Tax", "Current Tax Liabilities", {}),
	(
		"210301",
		"ITBIS por Pagar (Cobrado en Ventas)",
		"Tax",
		"Current Tax Liabilities",
		{"concepto": cat.ITBIS},
	),
	(
		"210302",
		"ITBIS Retenido a Terceros por Pagar",
		"Tax",
		"Current Tax Liabilities",
		{"concepto": cat.ITBIS_RETENIDO},
	),
	(
		"210303",
		"ISR Retenido a Terceros por Pagar (IR-17)",
		"Tax",
		"Current Tax Liabilities",
		{"concepto": cat.ISR_RETENIDO},
	),
	("210304", "ISR Retenido a Asalariados (IR-3)", "Tax", "Current Tax Liabilities", {}),
	("210305", "Anticipo de ISR por Pagar", "Tax", "Current Tax Liabilities", {}),
	("210306", "Impuesto sobre la Renta por Pagar (IR-2)", "Tax", "Current Tax Liabilities", {}),
	(
		"210307",
		"Impuesto Selectivo al Consumo por Pagar",
		"Tax",
		"Current Tax Liabilities",
		{"concepto": cat.ISC},
	),
	(
		"210308",
		"Otros Impuestos y Tasas por Pagar",
		"Tax",
		"Current Tax Liabilities",
		{"concepto": cat.OTROS_IMPUESTOS},
	),
	("210309", "Retención de Dividendos por Pagar", "Tax", "Current Tax Liabilities", {}),
	("2104", "Obligaciones Laborales", "", "Other Current Liabilities", {}),
	("210401", "Nómina por Pagar", "Payable", "Other Current Liabilities", {}),
	("210402", "TSS por Pagar (AFP, SFS y SRL)", "", "Other Current Liabilities", {}),
	("210403", "INFOTEP por Pagar", "", "Other Current Liabilities", {}),
	("210404", "Regalía Pascual por Pagar", "", "Short-term Provisions", {}),
	("210405", "Vacaciones por Pagar", "", "Short-term Provisions", {}),
	("210406", "Bonificaciones por Pagar", "", "Short-term Provisions", {}),
	(
		"210407",
		"Propina Legal por Pagar",
		"Tax",
		"Other Current Liabilities",
		{"concepto": cat.PROPINA_LEGAL},
	),
	("210408", "Reembolsos de Gastos a Empleados", "Payable", "Other Payables", {}),
	("2105", "Anticipos de Clientes", "", "Other Current Liabilities", {}),
	("210501", "Anticipos Recibidos de Clientes", "Receivable", "Other Current Liabilities", {}),
	("2106", "Préstamos a Corto Plazo", "", "Short-term Borrowings", {}),
	("210601", "Préstamos Bancarios a Corto Plazo", "", "Short-term Borrowings", {}),
	("210602", "Sobregiros Bancarios", "", "Short-term Borrowings", {}),
	("210603", "Tarjetas de Crédito Corporativas", "", "Short-term Borrowings", {}),
	("2107", "Dividendos por Pagar", "", "Other Current Liabilities", {}),
	("22", "PASIVOS NO CORRIENTES", "", "", {}),
	("2201", "Préstamos Bancarios a Largo Plazo", "", "Long-term Borrowings", {}),
	("2202", "Préstamos de Relacionadas a Largo Plazo", "", "Long-term Borrowings", {}),
	("2203", "Provisión para Prestaciones Laborales", "", "Long-term Provisions", {}),
	("2204", "Impuesto sobre la Renta Diferido Pasivo", "", "Other Non-current Liabilities", {}),
	# ------------------------------------------------------------------ PATRIMONIO
	("3", "PATRIMONIO", "", "", {}),
	("31", "Capital", "", "Share Capital", {}),
	("3101", "Capital Suscrito y Pagado", "Equity", "Share Capital", {}),
	("3102", "Aportes para Futuras Capitalizaciones", "Equity", "Share Capital", {}),
	("32", "Reservas", "", "Reserves and Surplus", {}),
	("3201", "Reserva Legal", "Equity", "Reserves and Surplus", {}),
	("3202", "Otras Reservas", "Equity", "Reserves and Surplus", {}),
	("33", "Resultados", "", "Reserves and Surplus", {}),
	("3301", "Resultados Acumulados", "Equity", "Reserves and Surplus", {}),
	("3302", "Resultado del Ejercicio", "Equity", "Reserves and Surplus", {}),
	("3303", "Balance de Apertura", "Equity", "Reserves and Surplus", {}),
	("3304", "Dividendos Declarados", "Equity", "Reserves and Surplus", {}),
	("34", "Superávit por Revaluación", "Equity", "Reserves and Surplus", {}),
	# ------------------------------------------------------------------ INGRESOS (tipo 607)
	("4", "INGRESOS", "", "", {}),
	("41", "Ingresos por Operaciones", "", "Revenue from Operations", {"ing": _ing(1)}),
	("4101", "Ventas de Bienes", "Income Account", "Revenue from Operations", {}),
	("4102", "Ventas de Servicios", "Income Account", "Revenue from Operations", {}),
	("4103", "Ventas al Exterior (Exportaciones)", "Income Account", "Revenue from Operations", {}),
	("4104", "Devoluciones en Ventas", "Income Account", "Revenue from Operations", {}),
	("4105", "Descuentos en Ventas", "Income Account", "Revenue from Operations", {}),
	("42", "Ingresos Financieros", "", "Investment Income", {"ing": _ing(2)}),
	("4201", "Intereses Ganados", "Income Account", "Investment Income", {}),
	("4202", "Otros Ingresos Financieros", "Income Account", "Investment Income", {}),
	("43", "Ingresos Extraordinarios", "", "Other Operating Income", {"ing": _ing(3)}),
	("4301", "Otros Ingresos Extraordinarios", "Income Account", "Other Operating Income", {}),
	("44", "Ingresos por Arrendamientos", "", "Other Operating Income", {"ing": _ing(4)}),
	("4401", "Alquileres Cobrados", "Income Account", "Other Operating Income", {}),
	("45", "Ingresos por Venta de Activos Depreciables", "", "Other Operating Income", {"ing": _ing(5)}),
	("4501", "Ganancia o Pérdida en Venta de Activos", "Income Account", "Other Operating Income", {}),
	("46", "Otros Ingresos", "", "Other Operating Income", {"ing": _ing(6)}),
	("4601", "Otros Ingresos", "Income Account", "Other Operating Income", {}),
	# ------------------------------------------------------------------ COSTOS (tipo 606: 09)
	("5", "COSTOS", "", "", {"tbs": _tbs(9)}),
	("51", "Costo de Ventas", "", "Cost of Goods Sold", {}),
	("5101", "Costo de Ventas", "Cost of Goods Sold", "Cost of Goods Sold", {}),
	("5102", "Costo de Servicios", "Cost of Goods Sold", "Cost of Goods Sold", {}),
	("5103", "Gastos Incluidos en la Valoración", "Expenses Included In Valuation", "Other Direct Costs", {}),
	(
		"5104",
		"Gastos Incluidos en la Valoración de Activos",
		"Expenses Included In Asset Valuation",
		"Other Direct Costs",
		{},
	),
	("5105", "Ajustes de Inventario", "Stock Adjustment", "Other Direct Costs", {}),
	("52", "Costos de Producción", "", "Other Direct Costs", {}),
	("5201", "Mano de Obra Directa", "", "Other Direct Costs", {}),
	("5202", "Costos Indirectos de Fabricación", "", "Other Direct Costs", {}),
	("5203", "Energía Eléctrica de Producción", "", "Other Direct Costs", {}),
	# ------------------------------------------------------------------ GASTOS (tipo 606)
	("6", "GASTOS", "", "", {}),
	("61", "Gastos de Personal", "", "Operating Expenses", {"tbs": _tbs(1)}),
	("6101", "Sueldos y Salarios", "", "Operating Expenses", {}),
	("6102", "Horas Extras", "", "Operating Expenses", {}),
	("6103", "Comisiones", "", "Operating Expenses", {}),
	("6104", "Bonificaciones", "", "Operating Expenses", {}),
	("6105", "Regalía Pascual", "", "Operating Expenses", {}),
	("6106", "Vacaciones", "", "Operating Expenses", {}),
	("6107", "Prestaciones Laborales", "", "Operating Expenses", {}),
	("6108", "Aportes Patronales TSS (AFP, SFS y SRL)", "", "Operating Expenses", {}),
	("6109", "INFOTEP", "", "Operating Expenses", {}),
	("6110", "Seguro Médico Complementario", "", "Operating Expenses", {}),
	("6111", "Reembolsos de Gastos a Empleados", "Expense Account", "Operating Expenses", {}),
	("6112", "Capacitación", "", "Operating Expenses", {}),
	("6113", "Otros Gastos de Personal", "", "Operating Expenses", {}),
	("62", "Gastos por Trabajos, Suministros y Servicios", "", "Operating Expenses", {"tbs": _tbs(2)}),
	("6201", "Honorarios Profesionales", "", "Operating Expenses", {}),
	("6202", "Energía Eléctrica", "", "Operating Expenses", {}),
	("6203", "Agua", "", "Operating Expenses", {}),
	("6204", "Teléfono e Internet", "", "Operating Expenses", {}),
	("6205", "Combustibles y Lubricantes", "", "Operating Expenses", {}),
	("6206", "Mantenimiento y Reparaciones", "", "Operating Expenses", {}),
	("6207", "Materiales de Oficina y Papelería", "", "Operating Expenses", {}),
	("6208", "Limpieza", "", "Operating Expenses", {}),
	("6209", "Seguridad y Vigilancia", "", "Operating Expenses", {}),
	("6210", "Fletes y Transporte", "Chargeable", "Operating Expenses", {}),
	("6211", "Mensajería", "", "Operating Expenses", {}),
	("6212", "Servicios de Tecnología y Software", "", "Operating Expenses", {}),
	("6213", "Cuotas y Suscripciones", "", "Operating Expenses", {}),
	("6214", "Otros Servicios", "", "Operating Expenses", {}),
	("63", "Arrendamientos", "", "Operating Expenses", {"tbs": _tbs(3)}),
	("6301", "Alquiler de Locales y Oficinas", "", "Operating Expenses", {}),
	("6302", "Alquiler de Equipos", "", "Operating Expenses", {}),
	("6303", "Alquiler de Vehículos", "", "Operating Expenses", {}),
	("64", "Gastos de Activos Fijos", "", "Operating Expenses", {"tbs": _tbs(4)}),
	("6401", "Depreciación", "Depreciation", "Operating Expenses", {}),
	("6402", "Amortización de Intangibles", "Depreciation", "Operating Expenses", {}),
	("6403", "Reparación de Activos Fijos", "", "Operating Expenses", {}),
	("6404", "Mantenimiento de Activos Fijos", "", "Operating Expenses", {}),
	("65", "Gastos de Representación", "", "Operating Expenses", {"tbs": _tbs(5)}),
	("6501", "Relaciones Públicas", "", "Operating Expenses", {}),
	("6502", "Publicidad y Promoción", "Chargeable", "Operating Expenses", {}),
	("6503", "Atenciones a Clientes", "", "Operating Expenses", {}),
	("6504", "Viajes y Viáticos", "", "Operating Expenses", {}),
	("6505", "Otros Gastos de Representación", "", "Operating Expenses", {}),
	("66", "Otras Deducciones Admitidas", "", "Operating Expenses", {"tbs": _tbs(6)}),
	("6601", "Impuestos y Tasas", "", "Operating Expenses", {}),
	("6602", "Donaciones", "", "Operating Expenses", {}),
	("6603", "Cuentas Incobrables", "", "Operating Expenses", {}),
	("6604", "Gastos Legales", "", "Operating Expenses", {}),
	("6605", "Gastos Varios", "Chargeable", "Operating Expenses", {}),
	("6606", "Ajustes y Diferencias Menores", "", "Operating Expenses", {}),
	("6607", "Redondeos", "Round Off", "Operating Expenses", {}),
	("67", "Gastos Financieros", "", "Finance Costs", {"tbs": _tbs(7)}),
	("6701", "Intereses Bancarios", "", "Finance Costs", {}),
	("6702", "Comisiones y Cargos Bancarios", "", "Finance Costs", {}),
	("6703", "Impuesto 0.15% sobre Cheques y Transferencias", "", "Finance Costs", {}),
	("6704", "Diferencia Cambiaria", "", "Finance Costs", {}),
	("6705", "Diferencia Cambiaria No Realizada", "", "Finance Costs", {}),
	("68", "Gastos Extraordinarios", "", "Operating Expenses", {"tbs": _tbs(8)}),
	("6801", "Gastos No Deducibles", "", "Operating Expenses", {}),
	("6802", "Multas y Recargos", "", "Operating Expenses", {}),
	("6803", "Otros Gastos Extraordinarios", "", "Operating Expenses", {}),
	("6804", "Impuesto sobre la Renta", "", "Tax Expense", {}),
	("69", "Gastos de Seguros", "", "Operating Expenses", {"tbs": _tbs(11)}),
	("6901", "Seguros de Vehículos", "", "Operating Expenses", {}),
	("6902", "Seguros de Propiedades y Equipos", "", "Operating Expenses", {}),
	("6903", "Otros Seguros", "", "Operating Expenses", {}),
]

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
			frappe.db.sql(
				f"UPDATE `tab{campo.parent}` SET `{campo.fieldname}` = NULL WHERE `{campo.fieldname}` IN %(c)s",
				{"c": nombres},
			)


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
