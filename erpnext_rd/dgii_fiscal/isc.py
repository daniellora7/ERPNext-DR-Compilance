"""Impuesto selectivo al consumo (ISC): cálculo en las ventas, tasas vigentes y requisitos.

Base legal: Código Tributario, título IV (Ley 11-92), modificado por la Ley 30-26.

- Alcohol (art. 367, b): monto específico por litro de alcohol absoluto (litros x grado) más el
  ad valorem sobre el precio de venta al por menor, que incluye envases, etiquetas y tapas.
- Cigarrillos (art. 367, c; art. 375, VIII): monto específico por cajetilla de 20 o de 10 más el 20%
  ad valorem sobre el precio de venta al por menor.
- Vapeadores y sus líquidos (art. 375, XI): 55% ad valorem sobre el precio de venta al por menor.
- Telecomunicaciones y seguros: ad valorem sobre el valor del servicio. Seguros de vida: 11% en
  2027, 6% en 2028 y exentos desde 2029 (art. 383, IV).

El ISC de los bienes lo pagan el fabricante al transferirlos y el importador en la aduana (lo
liquida la DGA en la declaración de importación): en la venta solo se calcula para los artículos
de producción local. Los servicios lo cobran al facturar.

Cálculo: la factura lleva una fila de impuesto con el tipo de cargo «ISC por artículo» (primera
fila, tasa 100). ERPNext toma la base de cada línea de `base_isc` (gancho
`erpnext_taxable_base_resolvers` de ERPNext v16, el mismo en el navegador), así el ISC queda por
línea en el detalle de impuestos. En los bienes la base del ITBIS incluye el ISC (art. 339, 1): las
filas de ITBIS sobre el neto pasan a «sobre el total de la fila anterior» (la del ISC). En los
servicios no (art. 339, 3).

Las tasas están en *Configuracion DGII* (tabla «Tasas del ISC»), con su vigencia.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from erpnext_rd.dgii_fiscal import catalogos as cat

TIPO_CARGO = "ISC por artículo"
DESCRIPCION = "Impuesto selectivo al consumo (ISC)"
DIA_VENCE = 20

ALCOHOL = "Alcohol"
TABACO = "Tabaco"
VAPEADORES = "Vapeadores"
COMBUSTIBLES = "Combustibles"
TELECOMUNICACIONES = "Telecomunicaciones"
SEGUROS = "Seguros"
SEGUROS_VIDA = "Seguros de vida"
BIENES = (ALCOHOL, TABACO, VAPEADORES, COMBUSTIBLES)
SERVICIOS = (TELECOMUNICACIONES, SEGUROS, SEGUROS_VIDA)
CATEGORIAS = (*BIENES, *SERVICIOS)

# Casilla del perfil tributario -> categorías del ISC que la empresa cobra
POR_ACTIVIDAD = {
	"isc_alcohol": (ALCOHOL,),
	"isc_tabaco": (TABACO, VAPEADORES),
	"isc_combustibles": (COMBUSTIBLES,),
	"isc_telecomunicaciones": (TELECOMUNICACIONES,),
	"isc_seguros": (SEGUROS, SEGUROS_VIDA),
}

PRODUCCION_LOCAL = "Producción local"
IMPORTADO = "Importado"
PRESENTACIONES = {20: "20 cigarrillos", 10: "10 cigarrillos"}

# Base del ad valorem del alcohol y el tabaco (campo de la tasa). La Ley 30-26 (art. 41) prohíbe
# deducir nada del precio al por menor; el formato del e-CF de la DGII (v1.0, anterior a esa ley)
# lo calcula sobre el precio sin ITBIS ni ISC: (PVP / (1 + ITBIS) - específico) / (1 + tasa).
BASE_INTEGRA = "PVP íntegro (Ley 30-26)"
BASE_NETA = "PVP neto (formato e-CF DGII)"

# Productos de la tabla I del formato del e-CF (codificación de impuestos adicionales). El código
# del específico es el de la tabla; el del ad valorem, 17 más.
PRODUCTOS_ALCOHOL = (
	"Cerveza",
	"Vinos de uva",
	"Vermut y demás vinos de uvas frescas",
	"Demás bebidas fermentadas",
	"Alcohol etílico sin desnaturalizar (80% o más)",
	"Alcohol etílico sin desnaturalizar (menos de 80%)",
	"Aguardientes de uva",
	"Whisky",
	"Ron y demás aguardientes de caña",
	"Gin y ginebra",
	"Vodka",
	"Licores",
	"Los demás (bebidas y alcoholes)",
)
PRODUCTOS_TABACO = ("Cigarrillos que contienen tabaco", "Los demás cigarrillos")
CODIGO_ALCOHOL = 6  # 006 cerveza … 018 los demás
CODIGO_TABACO = {20: 19, 10: 21}  # 019-020 cajetilla de 20, 021-022 de 10
AD_VALOREM_MAS = 17
CODIGOS_SERVICIOS = {SEGUROS: "003", TELECOMUNICACIONES: "004"}
# Unidades de medida del e-CF (tabla IV)
BOTELLA, CAJETILLA, LITRO, UNIDAD = 5, 7, 24, 43
# Tipos de e-CF que llevan el ISC del detalle (31, 32, 33, 34 y 45)
TIPOS_ECF_CON_ISC = (31, 32, 33, 34, 45)

# Unidad de la base del monto específico (columna del resumen)
UNIDADES = {
	ALCOHOL: "litros de alcohol absoluto",
	TABACO: "cajetillas",
	COMBUSTIBLES: "galones",
}

LEY_30_26 = "Ley 30-26"
_DGII_OCT_DIC_2026 = "DGII, montos del 1/10 al 31/12/2026"

# (categoría, presentación, desde, hasta, ad valorem %, monto específico, base legal)
TASAS_INICIALES = (
	(ALCOHOL, None, "2026-10-01", "2026-12-31", 10, 768.65, f"Art. 375; {_DGII_OCT_DIC_2026}"),
	(TABACO, PRESENTACIONES[20], "2026-10-01", "2026-12-31", 20, 65.02, f"Art. 375; {_DGII_OCT_DIC_2026}"),
	(TABACO, PRESENTACIONES[10], "2026-10-01", "2026-12-31", 20, 32.51, f"Art. 375; {_DGII_OCT_DIC_2026}"),
	(VAPEADORES, None, None, None, 55, 0, f"Art. 375, XI ({LEY_30_26}, art. 43)"),
	(TELECOMUNICACIONES, None, None, None, 10, 0, "Título IV, Ley 11-92"),
	(SEGUROS, None, None, None, 16, 0, "Art. 382 y 383, Ley 11-92"),
	(SEGUROS_VIDA, None, None, "2026-12-31", 16, 0, "Art. 383, Ley 11-92"),
	(SEGUROS_VIDA, None, "2027-01-01", "2027-12-31", 11, 0, f"Art. 383, IV ({LEY_30_26}, art. 48)"),
	(SEGUROS_VIDA, None, "2028-01-01", "2028-12-31", 6, 0, f"Art. 383, IV ({LEY_30_26}, art. 48)"),
	(SEGUROS_VIDA, None, "2029-01-01", None, 0, 0, f"Exentos (art. 383, IV; {LEY_30_26}, art. 48)"),
)

CAMPOS_ARTICULO = (
	"rd_isc_categoria",
	"rd_isc_producto",
	"rd_isc_origen",
	"rd_isc_envases",
	"rd_isc_grado",
	"rd_isc_litros",
	"rd_isc_cigarrillos",
	"rd_isc_cajetillas",
	"rd_isc_galones",
	"rd_isc_precio_por_menor",
)
# Lo que se guarda en cada línea de la factura (moneda de la empresa, salvo el unitario)
CAMPOS_LINEA = (
	"rd_isc_categoria",
	"rd_isc_unitario",
	"rd_isc_tasa",
	"rd_isc_base_especifica",
	"rd_isc_base_ad_valorem",
	"rd_isc_especifico",
	"rd_isc_ad_valorem",
)


# ---------------------------------------------------------------------- perfil y tasas


def categorias_de(company: str) -> set[str]:
	"""Categorías del ISC que la empresa cobra según su perfil tributario."""
	from erpnext_rd.rd_compliance.perfil import perfil

	p = perfil(company)
	return {c for campo, categorias in POR_ACTIVIDAD.items() if cint(p.get(campo)) for c in categorias}


def tasas() -> list[frappe._dict]:
	return frappe.get_all(
		"Tasa ISC",
		filters={"parenttype": "Configuracion DGII", "parent": "Configuracion DGII"},
		fields=[
			"categoria",
			"presentacion",
			"desde",
			"hasta",
			"ad_valorem",
			"monto_especifico",
			"base_ad_valorem",
			"base_legal",
		],
		order_by="idx",
	)


def tasa(categoria: str, fecha=None, presentacion: str | None = None) -> frappe._dict | None:
	"""La tasa vigente en `fecha` (la de inicio más reciente si se superponen)."""
	fecha = getdate(fecha or today())
	vigentes = [
		t
		for t in tasas()
		if t.categoria == categoria
		and (not presentacion or t.presentacion == presentacion)
		and (not t.desde or getdate(t.desde) <= fecha)
		and (not t.hasta or getdate(t.hasta) >= fecha)
	]
	if not vigentes:
		return None
	return max(vigentes, key=lambda t: getdate(t.desde) if t.desde else getdate("1900-01-01"))


def cargar_tasas_iniciales(conf):
	"""Primera carga de la tabla (instalación): luego las mantiene el usuario."""
	for categoria, presentacion, desde, hasta, ad_valorem, monto, base_legal in TASAS_INICIALES:
		conf.append(
			"tasas_isc",
			{
				"categoria": categoria,
				"presentacion": presentacion,
				"desde": desde,
				"hasta": hasta,
				"ad_valorem": ad_valorem,
				"monto_especifico": monto,
				"base_legal": base_legal,
			},
		)


def cuenta_isc(company: str) -> str | None:
	"""Cuenta del ISC por pagar de la empresa (concepto fiscal ISC en el catálogo de cuentas)."""
	cuentas = frappe.get_all(
		"Account",
		filters={"company": company, "rd_concepto_fiscal": cat.ISC, "is_group": 0, "disabled": 0},
		pluck="name",
		order_by="lft",
		limit=1,
	)
	return cuentas[0] if cuentas else None


# ---------------------------------------------------------------------- cálculo


def isc_unitario(company: str, item_code: str, fecha=None, tasa_itbis: float = 0) -> frappe._dict | None:
	"""ISC de una unidad de inventario del artículo (moneda de la empresa), o la tasa si es un servicio.

	None si la empresa no cobra el ISC de ese artículo (sin categoría, categoría que no está en su
	perfil o bien importado). Lanza un error si falta la tasa vigente o un dato del artículo.
	`tasa_itbis` solo se usa con la base neta del ad valorem.
	"""
	articulo = frappe.get_cached_value("Item", item_code, CAMPOS_ARTICULO, as_dict=True)
	if not articulo or not articulo.rd_isc_categoria:
		return None
	categoria = articulo.rd_isc_categoria
	if categoria not in categorias_de(company):
		return None
	if categoria in BIENES and articulo.rd_isc_origen == IMPORTADO:
		return None

	presentacion = PRESENTACIONES.get(cint(articulo.rd_isc_cigarrillos)) if categoria == TABACO else None
	t = tasa(categoria, fecha, presentacion)
	if not t:
		frappe.throw(
			_("No hay tasa del ISC de {0} vigente al {1}. Regístrela en Configuración DGII.").format(
				_(categoria) + (f" ({_(presentacion)})" if presentacion else ""),
				frappe.format(getdate(fecha or today()), "Date"),
			),
			title=_("Falta la tasa del ISC"),
		)
	resultado = frappe._dict(categoria=categoria, tasa=0.0, base_especifica=0.0, base_ad_valorem=0.0)
	if categoria in SERVICIOS:
		resultado.tasa = flt(t.ad_valorem)
		return resultado

	resultado.base_especifica = _base_especifica(item_code, categoria, articulo)
	resultado.especifico = resultado.base_especifica * flt(t.monto_especifico)
	if flt(t.ad_valorem):
		precio = flt(articulo.rd_isc_precio_por_menor)
		if precio <= 0:
			_falta_dato(item_code, "rd_isc_precio_por_menor")
		resultado.base_ad_valorem = _base_ad_valorem(precio, resultado.especifico, t, tasa_itbis)
	resultado.ad_valorem = resultado.base_ad_valorem * flt(t.ad_valorem) / 100
	resultado.unitario = resultado.especifico + resultado.ad_valorem
	return resultado


def _base_ad_valorem(precio: float, especifico: float, t, tasa_itbis: float) -> float:
	"""Base del ad valorem de una unidad: el precio al por menor o, con la base neta, sin ITBIS ni ISC."""
	if t.base_ad_valorem != BASE_NETA or t.categoria not in (ALCOHOL, TABACO):
		return precio
	return (precio / (1 + flt(tasa_itbis) / 100) - especifico) / (1 + flt(t.ad_valorem) / 100)


def _base_especifica(item_code: str, categoria: str, articulo) -> float:
	"""Litros de alcohol absoluto, cajetillas o galones de una unidad de inventario."""
	if categoria == ALCOHOL:
		if flt(articulo.rd_isc_litros) <= 0:
			_falta_dato(item_code, "rd_isc_litros")
		if flt(articulo.rd_isc_grado) <= 0:
			_falta_dato(item_code, "rd_isc_grado")
		return flt(articulo.rd_isc_litros) * flt(articulo.rd_isc_grado) / 100
	if categoria == TABACO:
		if not articulo.rd_isc_cigarrillos:
			_falta_dato(item_code, "rd_isc_cigarrillos")
		return flt(articulo.rd_isc_cajetillas) or 1
	if categoria == COMBUSTIBLES:
		if flt(articulo.rd_isc_galones) <= 0:
			_falta_dato(item_code, "rd_isc_galones")
		return flt(articulo.rd_isc_galones)
	return 0.0


def _falta_dato(item_code: str, campo: str):
	etiqueta = frappe.get_meta("Item").get_label(campo)
	frappe.throw(
		_("Falta «{0}» del artículo {1} para calcular el ISC.").format(_(etiqueta), item_code),
		title=_("Datos del ISC incompletos"),
	)


def _cantidad(item) -> float:
	"""Cantidad en la unidad de inventario (el ISC del artículo es por unidad de inventario)."""
	return flt(item.get("qty")) * (flt(item.get("conversion_factor")) or 1)


def base_isc(calc, item, tax) -> float:
	"""Gancho `erpnext_taxable_base_resolvers`: el ISC de la línea (la fila lleva tasa 100).

	Los servicios guardan su base y su ISC aquí, con el neto ya calculado (con descuentos).
	"""
	tasa_servicio = flt(item.get("rd_isc_tasa"))
	if tasa_servicio:
		item.rd_isc_base_ad_valorem = flt(item.get("base_net_amount"))
		item.rd_isc_ad_valorem = flt(item.rd_isc_base_ad_valorem * tasa_servicio / 100, 2)
		return flt(item.get("net_amount")) * tasa_servicio / 100
	return flt(item.get("rd_isc_unitario")) * _cantidad(item)


def aplicar(doc, method=None):
	"""doc_events before_validate (ventas): ISC de cada línea y la fila del ISC en los impuestos."""
	from erpnext_rd.dgii_fiscal import regimenes
	from erpnext_rd.dgii_fiscal.ncf import _no_aplica

	if _no_aplica(doc):
		return
	# Venta a un régimen especial con B14 / E44: sin ISC (Norma General 05-2019)
	categorias = set() if regimenes.es_venta_exenta(doc) else categorias_de(doc.company)
	fila = _fila_isc(doc)
	if not categorias and not fila:
		return

	if not doc.get("taxes") and doc.get("taxes_and_charges"):
		doc.append_taxes_from_master()
	fecha = doc.get("posting_date") or today()
	tasa_cambio = flt(doc.get("conversion_rate")) or 1
	hay_bienes = hay_servicios = False
	for item in doc.items:
		datos = (
			isc_unitario(doc.company, item.item_code, fecha, _tasa_itbis(doc, item))
			if item.item_code
			else None
		)
		_guardar_linea(item, datos, tasa_cambio)
		if datos:
			hay_bienes |= datos.categoria in BIENES
			hay_servicios |= datos.categoria in SERVICIOS

	if hay_bienes and hay_servicios:
		frappe.throw(
			_(
				"Facture por separado los bienes y los servicios con ISC: en los bienes el ITBIS se "
				"calcula sobre el precio más el ISC y en los servicios no (art. 339 del Código Tributario)."
			),
			title=_("ISC"),
		)

	if not (hay_bienes or hay_servicios):
		if fila:
			_quitar_fila(doc, fila)
		return

	fila = _fila_isc(doc) or _nueva_fila(doc)
	_primera(doc, fila)
	fila.rate = 100
	_itbis_sobre_isc(doc, fila, hay_bienes)


def _tasa_itbis(doc, item) -> float:
	"""Tasa del ITBIS de la línea: la de su plantilla por artículo o la de la fila del ITBIS."""
	import json

	from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta

	por_articulo = json.loads(item.get("item_tax_rate") or "{}")
	for t in doc.get("taxes") or []:
		if t.charge_type == TIPO_CARGO or t.get("add_deduct_tax") == "Deduct":
			continue
		if concepto_de_cuenta(t.account_head) == cat.ITBIS:
			return flt(por_articulo.get(t.account_head, t.rate))
	return 0.0


def _guardar_linea(item, datos, tasa_cambio: float):
	if not datos:
		for campo in CAMPOS_LINEA:
			item.set(campo, None if campo == "rd_isc_categoria" else 0)
		return
	cantidad = _cantidad(item)
	item.rd_isc_categoria = datos.categoria
	item.rd_isc_tasa = datos.tasa
	if datos.categoria in SERVICIOS:
		# La base y el ISC los guarda base_isc con el neto definitivo
		item.rd_isc_unitario = item.rd_isc_base_especifica = item.rd_isc_especifico = 0
		return
	item.rd_isc_unitario = flt(datos.unitario / tasa_cambio, 6)
	item.rd_isc_base_especifica = flt(datos.base_especifica * cantidad, 4)
	item.rd_isc_base_ad_valorem = flt(datos.base_ad_valorem * cantidad, 2)
	item.rd_isc_especifico = flt(datos.especifico * cantidad, 2)
	item.rd_isc_ad_valorem = flt(datos.ad_valorem * cantidad, 2)


def _fila_isc(doc):
	return next((t for t in doc.get("taxes") or [] if t.charge_type == TIPO_CARGO), None)


def _nueva_fila(doc):
	cuenta = cuenta_isc(doc.company)
	if not cuenta:
		frappe.throw(
			_(
				"La empresa {0} no tiene la cuenta del ISC por pagar. Márquela con el concepto fiscal «{1}» "
				"en el catálogo de cuentas."
			).format(doc.company, _(cat.ISC)),
			title=_("Falta la cuenta del ISC"),
		)
	return doc.append(
		"taxes",
		{
			"charge_type": TIPO_CARGO,
			"account_head": cuenta,
			"description": _(DESCRIPCION),
			"rate": 100,
			"cost_center": doc.get("cost_center")
			or frappe.get_cached_value("Company", doc.company, "cost_center"),
		},
	)


def _reordenar(doc, filas):
	"""Pone las filas en el orden dado y corrige las referencias a filas anteriores (row_id)."""
	nuevo_idx = {t.idx: i for i, t in enumerate(filas, 1) if t.idx}
	for i, t in enumerate(filas, 1):
		if t.get("row_id"):
			t.row_id = str(nuevo_idx.get(cint(t.row_id), t.row_id))
		t.idx = i
	doc.set("taxes", filas)


def _primera(doc, fila):
	"""La fila del ISC va primero: las del ITBIS de los bienes se calculan sobre su total."""
	if doc.taxes[0] is fila:
		return
	for i, t in enumerate(doc.taxes, 1):
		t.idx = t.idx or i
	_reordenar(doc, [fila, *(t for t in doc.taxes if t is not fila)])


def _quitar_fila(doc, fila):
	"""Sin líneas con ISC: se quita su fila y el ITBIS vuelve a calcularse sobre el neto."""
	for t in doc.taxes:
		if t.charge_type == "On Previous Row Total" and cint(t.row_id) == fila.idx:
			t.charge_type = "On Net Total"
			t.row_id = None
	_reordenar(doc, [t for t in doc.taxes if t is not fila])


def _itbis_sobre_isc(doc, fila, hay_bienes: bool):
	from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta

	for t in doc.taxes:
		if t is fila or t.get("add_deduct_tax") == "Deduct":
			continue
		if concepto_de_cuenta(t.account_head) != cat.ITBIS:
			continue
		if hay_bienes and t.charge_type == "On Net Total":
			if cint(t.included_in_print_rate):
				frappe.throw(
					_(
						"Con ISC, el ITBIS se calcula sobre el precio más el ISC (art. 339): quite "
						"«Incluido en el precio» de la fila del ITBIS."
					),
					title=_("ISC"),
				)
			t.charge_type = "On Previous Row Total"
			t.row_id = str(fila.idx)
		elif not hay_bienes and t.charge_type == "On Previous Row Total" and cint(t.row_id) == fila.idx:
			t.charge_type = "On Net Total"
			t.row_id = None


# ---------------------------------------------------------------------- resumen mensual


def resumen_mensual(company: str, anio: int, mes: int) -> list[frappe._dict]:
	"""ISC de las ventas del mes por categoría (las notas de crédito restan).

	Las facturas consolidadas del cierre de caja no cuentan: su ISC está en cada POS Invoice.
	"""
	from erpnext_rd.dgii_reportes.datos import rango

	desde, hasta = rango(anio, mes)
	por_categoria: dict[str, frappe._dict] = {}
	for doctype in ("Sales Invoice", "POS Invoice"):
		factura = frappe.qb.DocType(doctype)
		linea = frappe.qb.DocType(f"{doctype} Item")
		consulta = (
			frappe.qb.from_(linea)
			.join(factura)
			.on(factura.name == linea.parent)
			.select(
				linea.rd_isc_categoria,
				linea.rd_isc_base_especifica,
				linea.rd_isc_base_ad_valorem,
				linea.rd_isc_especifico,
				linea.rd_isc_ad_valorem,
			)
			.where(
				(factura.company == company)
				& (factura.docstatus == 1)
				& (factura.posting_date[desde:hasta])
				& linea.rd_isc_categoria.isnotnull()
				& (linea.rd_isc_categoria != "")
			)
		)
		if doctype == "Sales Invoice":
			consulta = consulta.where(factura.is_consolidated == 0)
		for fila in consulta.run(as_dict=True):
			total = por_categoria.setdefault(
				fila.rd_isc_categoria,
				frappe._dict(
					categoria=fila.rd_isc_categoria,
					unidad=UNIDADES.get(fila.rd_isc_categoria, ""),
					base_especifica=0.0,
					base_ad_valorem=0.0,
					especifico=0.0,
					ad_valorem=0.0,
				),
			)
			total.base_especifica += flt(fila.rd_isc_base_especifica)
			total.base_ad_valorem += flt(fila.rd_isc_base_ad_valorem)
			total.especifico += flt(fila.rd_isc_especifico)
			total.ad_valorem += flt(fila.rd_isc_ad_valorem)
	filas = [por_categoria[c] for c in CATEGORIAS if c in por_categoria]
	for f in filas:
		f.total = flt(f.especifico + f.ad_valorem, 2)
	return filas


# ---------------------------------------------------------------------- e-CF


def _con_isc(item) -> bool:
	return bool(flt(item.get("rd_isc_especifico")) or flt(item.get("rd_isc_ad_valorem")))


def validar_ecf(doc):
	"""Antes de emitir: el tipo de e-CF admite el ISC y cada línea tiene su código de la DGII."""
	lineas = [i for i in doc.items if _con_isc(i)]
	if not lineas:
		return
	tipo = (doc.get("rd_tipo_comprobante") or "")[1:]
	if cint(tipo) not in TIPOS_ECF_CON_ISC:
		frappe.throw(
			_("El e-CF {0} no lleva el ISC de los artículos: use E31, E32, E33, E34 o E45.").format(
				doc.get("rd_tipo_comprobante")
			),
			title=_("e-CF con ISC"),
		)
	for item in lineas:
		ecf_linea(doc, item)


def ecf_linea(doc, item) -> tuple[dict, list[frappe._dict]]:
	"""Datos del ISC de una línea para el e-CF (formato v1.0 de la DGII).

	Devuelve los campos del ítem (cantidad de referencia, subcantidad, grados, precio de referencia)
	y los impuestos adicionales de la línea: código de la tabla I, tasa y montos en la moneda de la
	factura. Lanza un error si la categoría no tiene código en la tabla o falta el producto.
	"""
	if not _con_isc(item):
		return {}, []
	conversion = flt(doc.get("conversion_rate")) or 1
	especifico = abs(flt(item.rd_isc_especifico)) / conversion
	ad_valorem = abs(flt(item.rd_isc_ad_valorem)) / conversion
	categoria = item.rd_isc_categoria

	if categoria in SERVICIOS:
		codigo = _codigo_servicio(doc, item)
		return {}, [frappe._dict(codigo=codigo, tasa=flt(item.rd_isc_tasa), otros=ad_valorem)]

	if categoria not in (ALCOHOL, TABACO):
		frappe.throw(
			_(
				"El ISC de {0} no tiene código en la tabla de impuestos adicionales del e-CF de la DGII: "
				"emita este comprobante desde la Facturación Gratuita de la DGII."
			).format(_(categoria)),
			title=_("e-CF con ISC"),
		)

	articulo = frappe.get_cached_value("Item", item.item_code, CAMPOS_ARTICULO, as_dict=True)
	productos = PRODUCTOS_ALCOHOL if categoria == ALCOHOL else PRODUCTOS_TABACO
	if articulo.rd_isc_producto not in productos:
		_falta_dato(item.item_code, "rd_isc_producto")
	indice = productos.index(articulo.rd_isc_producto)
	precio = flt(articulo.rd_isc_precio_por_menor) / conversion

	if categoria == ALCOHOL:
		envases = cint(articulo.rd_isc_envases) or 1
		t = tasa(ALCOHOL, doc.posting_date)
		codigo = CODIGO_ALCOHOL + indice
		campos = {
			"referencia": envases,
			"unidad_referencia": BOTELLA,
			"subcantidad": flt(articulo.rd_isc_litros) / envases,
			"codigo_subcantidad": LITRO,
			"grados": flt(articulo.rd_isc_grado),
			"precio_referencia": precio / envases,
		}
	else:
		cigarrillos = cint(articulo.rd_isc_cigarrillos)
		cajetillas = flt(articulo.rd_isc_cajetillas) or 1
		t = tasa(TABACO, doc.posting_date, PRESENTACIONES.get(cigarrillos))
		codigo = CODIGO_TABACO[cigarrillos] + indice
		campos = {
			"referencia": cajetillas,
			"unidad_referencia": CAJETILLA,
			"subcantidad": cigarrillos,
			"codigo_subcantidad": UNIDAD,
			"precio_referencia": precio / cajetillas,
		}

	impuestos = []
	if especifico:
		impuestos.append(
			frappe._dict(codigo=f"{codigo:03d}", tasa=flt(t.monto_especifico), especifico=especifico)
		)
	if ad_valorem:
		impuestos.append(
			frappe._dict(
				codigo=f"{codigo + AD_VALOREM_MAS:03d}", tasa=flt(t.ad_valorem), ad_valorem=ad_valorem
			)
		)
	return campos, impuestos


def _codigo_servicio(doc, item) -> str:
	"""Seguros y telecomunicaciones (003, 004). Los seguros de vida usan el 003 solo con su misma tasa."""
	categoria = item.rd_isc_categoria
	if categoria == SEGUROS_VIDA:
		seguros = tasa(SEGUROS, doc.posting_date)
		if seguros and flt(seguros.ad_valorem) == flt(item.rd_isc_tasa):
			categoria = SEGUROS
	if categoria not in CODIGOS_SERVICIOS:
		frappe.throw(
			_(
				"El ISC de {0} al {1}% no tiene código en la tabla de impuestos adicionales del e-CF de la "
				"DGII: emita este comprobante desde la Facturación Gratuita de la DGII."
			).format(_(item.rd_isc_categoria), flt(item.rd_isc_tasa)),
			title=_("e-CF con ISC"),
		)
	return CODIGOS_SERVICIOS[categoria]


# ---------------------------------------------------------------------- navegador


@frappe.whitelist()
def isc_de_articulo(
	company: str, item_code: str, fecha: str | None = None, tasa_itbis: float = 0
) -> dict | None:
	"""Para el formulario: ISC por unidad (moneda de la empresa) o tasa del servicio.

	Es una vista previa: al guardar, el servidor lo recalcula con la tasa del ITBIS de la línea.
	"""
	frappe.has_permission("Item", "read", item_code, throw=True)
	try:
		datos = isc_unitario(company, item_code, fecha, flt(tasa_itbis))
	except frappe.ValidationError:
		frappe.clear_messages()
		return None
	if not datos:
		return None
	return {"categoria": datos.categoria, "unitario": flt(datos.get("unitario")), "tasa": datos.tasa}
