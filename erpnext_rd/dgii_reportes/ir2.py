"""Apoyo para la declaración jurada del ISR de las personas jurídicas (IR-2).

No es la declaración: es el papel de trabajo para llenar los anexos D, D-1, D-2 y G y la liquidación.
Cada *Cuadre Fiscal IR2* (empresa y ejercicio) toma los saldos fiscales finales del cuadre del año
anterior; el primer año parte del valor en libros, que se reemplaza por el costo fiscal del IR-2
anterior.

- Ajuste por inflación (anexo D-2, art. 327 y Decreto 1520-04): la base es el menor entre el
  patrimonio fiscal y los activos no monetarios al inicio del ejercicio; el ajuste es la base por
  (multiplicador - 1). El multiplicador de cada cierre lo publica la DGII (tabla en *Configuracion
  DGII*). El ajuste se distribuye entre los activos no monetarios según su peso: el del inventario es
  un ajuste negativo (anexo G, 2.2) y el de los activos depreciables aumenta su costo fiscal.
- Depreciación fiscal (art. 287, literal e):
  - Categoría 1 (edificaciones): cuenta separada por activo, 5% del costo fiscal ajustado. Lo que
    entra o sale en el año se deprecia por los meses en servicio (anexo D-1).
  - Categorías 2 (vehículos livianos, equipo y muebles de oficina, computadoras) y 3 (lo demás):
    una cuenta por categoría, 25% y 15% del balance al cierre. Las adiciones entran mitad este año y
    mitad el siguiente; los retiros salen por el valor de la transferencia (anexo D). Los bienes dados
    en arrendamiento llevan su propia cuenta al 50% y 30%.
  - Las tasas están en *Configuracion DGII*.
- Cuadre contable-fiscal (anexo G y liquidación): beneficio contable + ajustes positivos - ajustes
  negativos - pérdidas compensables = renta neta imponible; por la tasa del ISR da el impuesto
  liquidado, del que se restan los anticipos y los créditos.

La diferencia entre la depreciación contable (asientos de depreciación de los activos) y la fiscal
pasa al anexo G como exceso (positivo) o deficiencia (negativo).
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate

from erpnext_rd.dgii_fiscal.consulta_ncf import INVALIDOS

DOCTYPE = "Cuadre Fiscal IR2"
CONFIGURACION = "Configuracion DGII"

CATEGORIA_1 = "Categoría 1"
CATEGORIA_2 = "Categoría 2"
CATEGORIA_3 = "Categoría 3"
TERRENO = "Terreno"
CATEGORIAS = (CATEGORIA_1, CATEGORIA_2, CATEGORIA_3, TERRENO)

PROPIO = "Uso propio"
ARRENDAMIENTO = "Dado en arrendamiento"
INVENTARIO = "Inventario"
OTROS_ACTIVOS = "Otros activos no monetarios"

POSITIVO = "Positivo"
NEGATIVO = "Negativo"
AUTOMATICO = "Automático"
MANUAL = "Manual"

# Anexo G del IR-2
EXCESO_DEPRECIACION = "1.2 Exceso en depreciación"
GASTOS_SIN_COMPROBANTE = "1.13 Gastos sin comprobantes con valor fiscal"
DEFICIENCIA_DEPRECIACION = "2.1 Deficiencia en depreciación"
AJUSTE_INVENTARIO = "2.2 Ajustes de inventario (D-2)"
CONCEPTOS_POSITIVOS = (
	"1.1 Impuestos no deducibles",
	EXCESO_DEPRECIACION,
	"1.3 Ajustes por fiscalización de ejercicios anteriores",
	"1.4 Exceso provisión cuentas incobrables",
	"1.5 Exceso donaciones a instituciones de bien público",
	"1.6 Pérdida de capital no compensable",
	"1.7 Diferencia cambiaria",
	"1.8 Ajustes positivos por reembolsos",
	"1.9 Ajustes de precios de transferencia",
	"1.10 Gastos de intereses no deducibles",
	"1.11 Otros gastos no admitidos (art. 288)",
	"1.12 Ajustes de inventarios",
	GASTOS_SIN_COMPROBANTE,
	"1.14 Impuesto sobre la renta diferido",
	"1.15 Provisiones no admitidas",
	"1.16 Pasivo no sustentado",
	"1.17 Otros ajustes positivos",
)
CONCEPTOS_NEGATIVOS = (
	DEFICIENCIA_DEPRECIACION,
	AJUSTE_INVENTARIO,
	"2.3 Diferencia cambiaria",
	"2.4 Otros ajustes negativos",
)
# Los que se recalculan en cada guardado (los demás automáticos solo al traer los datos)
CONCEPTOS_CALCULADOS = (EXCESO_DEPRECIACION, DEFICIENCIA_DEPRECIACION, AJUSTE_INVENTARIO)

CAMPOS_TASA = {
	(CATEGORIA_1, PROPIO): "depreciacion_categoria_1",
	(CATEGORIA_2, PROPIO): "depreciacion_categoria_2",
	(CATEGORIA_3, PROPIO): "depreciacion_categoria_3",
	(CATEGORIA_2, ARRENDAMIENTO): "depreciacion_arrendamiento_2",
	(CATEGORIA_3, ARRENDAMIENTO): "depreciacion_arrendamiento_3",
}
TASAS_POR_DEFECTO = {
	"depreciacion_categoria_1": 5,
	"depreciacion_categoria_2": 25,
	"depreciacion_categoria_3": 15,
	"depreciacion_arrendamiento_2": 50,
	"depreciacion_arrendamiento_3": 30,
	"tasa_isr_juridicas": 27,
}
CUENTAS = (
	(CATEGORIA_2, PROPIO),
	(CATEGORIA_3, PROPIO),
	(CATEGORIA_2, ARRENDAMIENTO),
	(CATEGORIA_3, ARRENDAMIENTO),
)

# Multiplicadores publicados por la DGII (resoluciones informativas de cada cierre)
MULTIPLICADORES = (
	("2024-12-31", 1.0335, "DDG-AR1-2025-00001"),
	("2025-12-31", 1.0495, "DDG-AR1-2026-00001"),
)


# ---------------------------------------------------------------------- configuración


def tasa(campo: str) -> float:
	valor = frappe.db.get_single_value(CONFIGURACION, campo)
	return flt(valor) if valor is not None and valor != "" else flt(TASAS_POR_DEFECTO[campo])


def tasa_depreciacion(categoria: str, uso: str = PROPIO) -> float:
	return tasa(CAMPOS_TASA[(categoria, uso)])


def multiplicador(cierre) -> float | None:
	"""Multiplicador del ajuste por inflación para el ejercicio cerrado en `cierre`."""
	valor = frappe.db.get_value(
		"Multiplicador Inflacion DGII",
		{"parent": CONFIGURACION, "cierre": getdate(cierre)},
		"multiplicador",
	)
	return flt(valor) if valor else None


# ---------------------------------------------------------------------- cálculos


def meses_en_servicio(inicio, fin) -> int:
	"""Meses calendario de `inicio` a `fin`, ambos incluidos (anexo D-1: del 2/6 al 31/12 son 7)."""
	inicio, fin = getdate(inicio), getdate(fin)
	return max((fin.year - inicio.year) * 12 + fin.month - inicio.month + 1, 0)


def depreciar_edificacion(
	costo_inicial: float,
	ajuste: float,
	adicion: float,
	fecha_adicion,
	fecha_retiro,
	desde,
	hasta,
	tasa_anual: float,
) -> frappe._dict:
	"""Categoría 1: el costo que viene del año anterior (con su ajuste) se deprecia por los meses en
	servicio del año; una adición (compra o mejora) desde el mes en que entra en servicio."""
	existente = flt(costo_inicial) + flt(ajuste)
	fin = getdate(fecha_retiro) if fecha_retiro else getdate(hasta)
	meses = meses_en_servicio(desde, fin) if existente else 0
	meses_adicion = meses_en_servicio(max(getdate(fecha_adicion), getdate(desde)), fin) if adicion else 0
	base = flt(existente * meses / 12 + flt(adicion) * meses_adicion / 12, 2)
	depreciacion = flt(base * flt(tasa_anual) / 100, 2)
	return frappe._dict(
		meses=max(meses, meses_adicion),
		base=base,
		depreciacion=depreciacion,
		costo_final=flt(existente + flt(adicion) - depreciacion, 2),
	)


def depreciar_cuenta(
	balance_inicial: float, ajuste: float, adiciones: float, retiros: float, tasa_anual: float
) -> frappe._dict:
	"""Categorías 2 y 3 (anexo D): la mitad de las adiciones entra en la base de este año y la otra
	mitad se suma al costo fiscal final, que es el balance inicial del año siguiente."""
	imponibles = flt(flt(adiciones) / 2, 2)
	no_depreciada = flt(flt(adiciones) - imponibles, 2)
	base = flt(flt(balance_inicial) + flt(ajuste) + imponibles - flt(retiros), 2)
	depreciacion = flt(max(base, 0) * flt(tasa_anual) / 100, 2)
	return frappe._dict(
		adiciones_imponibles=imponibles,
		adicion_no_depreciada=no_depreciada,
		base=base,
		depreciacion=depreciacion,
		costo_final=flt(base - depreciacion + no_depreciada, 2),
	)


def distribuir_ajuste(patrimonio: float, valores: list[tuple[str, float]], factor: float) -> frappe._dict:
	"""Anexo D-2: ajuste = menor(patrimonio fiscal, activos no monetarios) x (multiplicador - 1),
	repartido entre los activos no monetarios según su valor fiscal."""
	no_monetarios = flt(sum(max(flt(v), 0) for _c, v in valores), 2)
	base = flt(max(min(flt(patrimonio), no_monetarios), 0), 2)
	ajuste = flt(base * (flt(factor) - 1), 2) if flt(factor) > 1 else 0.0
	filas, repartido = [], 0.0
	positivos = [(c, flt(v)) for c, v in valores if flt(v) > 0]
	for i, (concepto, valor) in enumerate(positivos):
		if i == len(positivos) - 1:
			parte = flt(ajuste - repartido, 2)
		else:
			parte = flt(ajuste * valor / no_monetarios, 2)
			repartido += parte
		filas.append(
			frappe._dict(concepto=concepto, valor=valor, porcentaje=valor * 100 / no_monetarios, ajuste=parte)
		)
	return frappe._dict(activos_no_monetarios=no_monetarios, base=base, ajuste=ajuste, filas=filas)


def liquidar(
	beneficio: float, positivos: float, negativos: float, perdidas: float, tasa_isr: float, creditos: float
) -> frappe._dict:
	renta_antes = flt(flt(beneficio) + flt(positivos) - flt(negativos), 2)
	renta = flt(max(renta_antes - flt(perdidas), 0), 2)
	impuesto = flt(renta * flt(tasa_isr) / 100, 2)
	diferencia = flt(impuesto - flt(creditos), 2)
	return frappe._dict(
		renta_antes_perdidas=renta_antes,
		renta_neta_imponible=renta,
		impuesto_liquidado=impuesto,
		diferencia_pagar=max(diferencia, 0),
		saldo_favor=max(-diferencia, 0),
	)


# ---------------------------------------------------------------------- datos de ERPNext


def categoria_fiscal(asset_category: str) -> str:
	"""Categoría del art. 287 de la categoría de activo. Sin indicar: terreno si no se deprecia y
	categoría 3 (la residual) en los demás casos."""
	categoria, no_depreciable = frappe.get_cached_value(
		"Asset Category", asset_category, ["rd_categoria_fiscal", "non_depreciable_category"]
	)
	return categoria or (TERRENO if no_depreciable else CATEGORIA_3)


def activos(company: str, desde, hasta) -> list[frappe._dict]:
	"""Activos validados que estuvieron en la empresa en algún momento del ejercicio."""
	desde, hasta = getdate(desde), getdate(hasta)
	filas = frappe.get_all(
		"Asset",
		filters={"company": company, "docstatus": 1},
		fields=[
			"name",
			"asset_name",
			"asset_category",
			"rd_dado_en_arrendamiento",
			"purchase_date",
			"available_for_use_date",
			"total_asset_cost",
			"opening_accumulated_depreciation",
			"disposal_date",
			"default_finance_book",
		],
		order_by="available_for_use_date, name",
	)
	resultado = []
	for a in filas:
		a.categoria = categoria_fiscal(a.asset_category)
		a.uso = ARRENDAMIENTO if a.rd_dado_en_arrendamiento else PROPIO
		# Art. 287, VII: la categoría 1 entra al ponerse en servicio; las demás, al adquirirse
		ingreso = a.available_for_use_date if a.categoria == CATEGORIA_1 else a.purchase_date
		a.ingreso = getdate(ingreso or a.available_for_use_date or a.purchase_date)
		a.retiro = getdate(a.disposal_date) if a.disposal_date else None
		if a.ingreso > hasta or (a.retiro and a.retiro < desde):
			continue
		a.adicion = desde <= a.ingreso <= hasta
		a.retirado = bool(a.retiro and a.retiro <= hasta)
		resultado.append(a)
	return resultado


def depreciacion_contable(company: str, desde, hasta) -> dict[str, float]:
	"""Depreciación registrada por activo (asientos de depreciación validados) en el rango."""
	filtro_desde = "AND je.posting_date >= %(desde)s" if desde else ""
	filas = frappe.db.sql(
		f"""
		SELECT ads.asset, SUM(ds.depreciation_amount)
		FROM `tabDepreciation Schedule` ds
		JOIN `tabAsset Depreciation Schedule` ads ON ads.name = ds.parent
		JOIN `tabAsset` a ON a.name = ads.asset
		JOIN `tabJournal Entry` je ON je.name = ds.journal_entry
		WHERE ads.docstatus = 1 AND je.docstatus = 1 AND ads.company = %(company)s
			AND IFNULL(ads.finance_book, '') = IFNULL(a.default_finance_book, '')
			AND je.posting_date <= %(hasta)s {filtro_desde}
		GROUP BY ads.asset
		""",
		{"company": company, "desde": desde, "hasta": hasta},
	)
	return {asset: flt(monto) for asset, monto in filas}


def valor_retiro(asset: str) -> float:
	"""Valor de la transferencia: lo facturado por el activo (0 si se desechó)."""
	return flt(
		frappe.db.sql(
			"""SELECT SUM(i.base_net_amount) FROM `tabSales Invoice Item` i
			JOIN `tabSales Invoice` s ON s.name = i.parent
			WHERE i.asset = %s AND s.docstatus = 1""",
			asset,
		)[0][0]
	)


def _saldo(company: str, fecha, condicion: str) -> float:
	"""Saldo deudor (débito - crédito) a `fecha` de las cuentas que cumplen `condicion`."""
	return flt(
		frappe.db.sql(
			f"""SELECT SUM(g.debit - g.credit)
			FROM `tabGL Entry` g JOIN `tabAccount` acc ON acc.name = g.account
			WHERE g.company = %(company)s AND g.is_cancelled = 0 AND g.posting_date <= %(fecha)s
				AND {condicion}""",
			{"company": company, "fecha": fecha},
		)[0][0],
		2,
	)


def patrimonio_contable(company: str, fecha) -> float:
	"""Activos menos pasivos en libros a `fecha` (punto de partida del patrimonio fiscal)."""
	return _saldo(company, fecha, "acc.root_type IN ('Asset', 'Liability')")


def inventario_contable(company: str, fecha) -> float:
	return _saldo(company, fecha, "acc.account_type = 'Stock'")


def resultado_contable(company: str, desde, hasta) -> frappe._dict:
	"""Ingresos y beneficio del ejercicio, sin el asiento de cierre del período."""
	ingresos, gastos = frappe.db.sql(
		"""SELECT
			SUM(IF(acc.root_type = 'Income', g.credit - g.debit, 0)),
			SUM(IF(acc.root_type = 'Expense', g.debit - g.credit, 0))
		FROM `tabGL Entry` g JOIN `tabAccount` acc ON acc.name = g.account
		WHERE g.company = %(company)s AND g.is_cancelled = 0
			AND g.posting_date BETWEEN %(desde)s AND %(hasta)s
			AND g.voucher_type != 'Period Closing Voucher'
			AND acc.root_type IN ('Income', 'Expense')""",
		{"company": company, "desde": desde, "hasta": hasta},
	)[0]
	return frappe._dict(ingresos=flt(ingresos, 2), beneficio=flt(flt(ingresos) - flt(gastos), 2))


def gastos_con_ncf_invalido(company: str, desde, hasta) -> float:
	"""Compras con NCF vencido o que no corresponde al RNC según la consulta de la DGII."""
	return flt(
		frappe.db.sql(
			"""SELECT SUM(base_net_total) FROM `tabPurchase Invoice`
			WHERE company = %(company)s AND docstatus = 1 AND posting_date BETWEEN %(desde)s AND %(hasta)s
				AND rd_ncf_estado_dgii IN %(estados)s""",
			{"company": company, "desde": desde, "hasta": hasta, "estados": INVALIDOS},
		)[0][0],
		2,
	)


def anticipos_del_ejercicio(company: str, desde, hasta) -> float:
	"""Anticipos que vencen dentro del ejercicio (el de cada mes vence el 15 del siguiente)."""
	from erpnext_rd.dgii_reportes import anticipos

	desde, hasta = getdate(desde), getdate(hasta)
	total, periodo = 0.0, add_months(date(desde.year, desde.month, 1), -1)
	while periodo <= hasta:
		a = anticipos.anticipo(company, periodo.year, periodo.month)
		if a and desde <= getdate(a.vence) <= hasta:
			total += a.cuota
		periodo = add_months(periodo, 1)
	return flt(total, 2)


def cuadre_anterior(company: str, ejercicio: int, excluir: str | None = None):
	nombres = frappe.get_all(
		DOCTYPE,
		filters={
			"company": company,
			"ejercicio": cint(ejercicio) - 1,
			"docstatus": ("<", 2),
			"name": ("!=", excluir or ""),
		},
		order_by="docstatus desc, modified desc",
		pluck="name",
		limit=1,
	)
	return frappe.get_doc(DOCTYPE, nombres[0]) if nombres else None


# ---------------------------------------------------------------------- botones del formulario


@frappe.whitelist()
def traer_datos(name: str):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	doc.traer_datos()
	doc.save()
	return doc.name


@frappe.whitelist()
def crear_base_anticipos(name: str) -> str:
	"""Base de los anticipos del año siguiente con los ingresos y el impuesto de este cuadre."""
	from erpnext_rd.dgii_reportes import anticipos

	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	existente = frappe.db.exists(anticipos.DOCTYPE, {"company": doc.company, "ejercicio": doc.ejercicio})
	if existente:
		return existente
	base = frappe.get_doc(
		{
			"doctype": anticipos.DOCTYPE,
			"company": doc.company,
			"ejercicio": doc.ejercicio,
			"ingresos_brutos": doc.ingresos_brutos,
			"impuesto_liquidado": doc.impuesto_liquidado,
		}
	).insert()
	frappe.msgprint(_("Base de anticipos {0} creada").format(base.name), indicator="green", alert=True)
	return base.name
