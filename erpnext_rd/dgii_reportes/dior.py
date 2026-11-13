"""Operaciones con partes relacionadas (Fase 8.3): apoyo para la DIOR.

Base (página de Precios de Transferencia de la DGII, leída el 2026-11-11): presentan la Declaración
Informativa de Operaciones con Relacionados (DIOR) los contribuyentes que operan con partes
relacionadas residentes o del exterior, o con jurisdicciones de baja o nula tributación (Código
Tributario arts. 281 a 281 quáter, Reglamento 78-14). Se presenta cada año en la Oficina Virtual, a
más tardar 60 días después del vencimiento del IR-2 (art. 281, párrafos I y IV; instructivo de envío
de la DIOR, DGII, mayo de 2026).

La app reúne las ventas y compras del ejercicio con los clientes y proveedores marcados como parte
relacionada, por contraparte, y arma la «Hoja de Detalle» que se pega en la Oficina Virtual (pestañas
Empresas y Operaciones de la versión 6, con las columnas y códigos del instructivo). El código de país
de la DGII, el tipo de persona, la actividad y los datos del estudio de precios de transferencia (método,
cuartiles, ajustes) se completan a mano: la app no los conoce.
"""

from datetime import date

import frappe
from frappe.query_builder.functions import Count, IfNull, Sum
from frappe.utils import add_days, flt, getdate

# Días después del vencimiento del IR-2
DIAS_DESPUES_IR2 = 60
# Códigos del supuesto de vinculación del instructivo (art. 281, modificado por la Ley 253-12)
SUPUESTOS_VINCULACION = (
	"1 - Párrafo I, literal II",
	"2 - Párrafo IV, numeral 1",
	"3 - Párrafo IV, numeral 2",
	"4 - Párrafo IV, numeral 3",
	"5 - Párrafo IV, numeral 4",
	"6 - Párrafo IV, numeral 5",
	"7 - Párrafo IV, numeral 6",
	"8 - Párrafo IV, numeral 7",
	"9 - Párrafo IV, numeral 8, literal I",
	"10 - Párrafo IV, numeral 8, literal II",
	"11 - Párrafo IV, numeral 8, literal III",
	"12 - Párrafo IV, numeral 8, literal IV",
	"13 - Párrafo IV, numeral 8, literal V",
	"14 - Párrafo IV, numeral 8, literal VI",
	"15 - Párrafo IV, numeral 9",
	"16 - Párrafo IV, numeral 10",
)
# Monedas de la lista del instructivo (las demás se declaran en pesos con la tasa 1)
MONEDAS = ("CAD", "CHF", "DKK", "EUR", "GBP", "JPY", "MXN", "NOK", "DOP", "SCP", "SEK", "USD", "VEF")
# Códigos de operación propuestos (el contador los revisa): ingresos 1xx, costo/gasto 2xx, activo 3xx
EXPORTACION = "101"
VENTA_BIENES = "127"
VENTA_ACTIVOS = "129"
VENTA_SERVICIOS = "125"
COMPRA_BIENES = "312"
IMPORTACION_BIENES = "302"
COMPRA_ACTIVOS = "313"
IMPORTACION_ACTIVOS = "303"
COMPRA_SERVICIOS = "221"
VENTA = "Venta"
COMPRA = "Compra"
ASIENTO = "Asiento"


def fecha_limite(cierre) -> date:
	"""Último día para presentar la DIOR del ejercicio cerrado en `cierre`: 60 días después del
	vencimiento del IR-2 (sin correr a día hábil)."""
	from erpnext_rd.dgii_reportes import ir2

	return add_days(ir2.fecha_limite(cierre), DIAS_DESPUES_IR2)


def relacionados() -> dict[str, list[str]]:
	return {
		"Customer": frappe.get_all("Customer", filters={"rd_parte_relacionada": 1}, pluck="name"),
		"Supplier": frappe.get_all("Supplier", filters={"rd_parte_relacionada": 1}, pluck="name"),
	}


def operaciones(company: str, desde, hasta) -> list[frappe._dict]:
	"""Ventas y compras aprobadas del período con partes relacionadas, por contraparte y tipo, y los
	asientos con ellas que no pagan facturas (préstamos, anticipos, cargos entre compañías...).

	Montos netos de ITBIS en la moneda de la empresa; las notas de crédito restan."""
	partes = relacionados()
	filas = []
	for doctype, parte, campo_parte, tipo in (
		("Sales Invoice", "Customer", "customer", VENTA),
		("Purchase Invoice", "Supplier", "supplier", COMPRA),
	):
		if not partes[parte]:
			continue
		for f in frappe.get_all(
			doctype,
			filters={
				"company": company,
				"docstatus": 1,
				campo_parte: ("in", partes[parte]),
				"posting_date": ("between", (getdate(desde), getdate(hasta))),
			},
			fields=[
				campo_parte,
				{"SUM": "base_net_total", "as": "monto"},
				{"COUNT": "name", "as": "documentos"},
			],
			group_by=campo_parte,
		):
			filas.append(_fila(parte, f[campo_parte], tipo, documentos=f.documentos, monto=flt(f.monto)))
	filas += asientos(company, desde, hasta, partes)
	return sorted(filas, key=lambda f: (f.nombre or "", f.tipo))


def _fila(parte: str, contraparte: str, tipo: str, **montos) -> frappe._dict:
	campo_nombre = "customer_name" if parte == "Customer" else "supplier_name"
	datos = frappe.db.get_value(
		parte,
		contraparte,
		["tax_id", "rd_vinculacion", campo_nombre] + (["country"] if parte == "Supplier" else []),
		as_dict=True,
	)
	return frappe._dict(
		tipo=tipo,
		parte=parte,
		contraparte=contraparte,
		nombre=datos.get(campo_nombre),
		identificacion=datos.tax_id,
		pais=datos.get("country"),
		vinculacion=datos.rd_vinculacion,
		**montos,
	)


def asientos(company: str, desde, hasta, partes: dict | None = None) -> list[frappe._dict]:
	"""Asientos validados del período con partes relacionadas que no pagan ni cruzan facturas:
	préstamos, anticipos y otras operaciones. Cargos y abonos por contraparte, sin compensarlos
	(un préstamo dado y cobrado en el año son dos operaciones)."""
	partes = partes or relacionados()
	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	filas = []
	for parte, nombres in partes.items():
		if not nombres:
			continue
		for party, cargos, abonos, documentos in (
			frappe.qb.from_(jea)
			.join(je)
			.on(jea.parent == je.name)
			.select(
				jea.party,
				Sum(jea.debit),
				Sum(jea.credit),
				Count(je.name).distinct(),
			)
			.where(
				(je.company == company)
				& (je.docstatus == 1)
				& (je.posting_date[getdate(desde) : getdate(hasta)])
				& (jea.party_type == parte)
				& (jea.party.isin(nombres))
				& (IfNull(jea.reference_type, "").notin(("Sales Invoice", "Purchase Invoice")))
			)
			.groupby(jea.party)
			.run()
		):
			filas.append(
				_fila(
					parte,
					party,
					ASIENTO,
					documentos=documentos,
					cargos=flt(cargos),
					abonos=flt(abonos),
				)
			)
	return filas


# ---------------------------------------------------------------------- Hoja de Detalle (versión 6)

COLUMNAS_EMPRESAS = (
	"Nombre o Razón Social",
	"Número Identificación Tributaria",
	"Código País Domicilio Fiscal",
	"Código Tipo de Persona",
	"Actividad Económica",
	"Dirección",
	"Código Supuesto de Vinculación",
)
COLUMNAS_OPERACIONES = (
	"Persona Física, Jurídica o Entidad Relacionada",
	"Código Operación",
	"Descripción Bien o Servicio",
	"Valor en Moneda Original",
	"Código Tipo Moneda",
	"Tasa de Cambio",
	"Monto Operación",
	"Monto del Principal",
	"Plazo en Días",
	"Tasa de Interés",
	"APA",
	"Margen o Precio de Transferencia",
	"Porcentaje (%)",
)
DESCRIPCIONES = {
	EXPORTACION: "Exportacion de bienes",
	"120": "Exportacion de activos fijos",
	VENTA_BIENES: "Venta local de bienes",
	VENTA_ACTIVOS: "Venta local de activos fijos",
	VENTA_SERVICIOS: "Prestacion de servicios",
	"131": "Nota de credito",
	COMPRA_BIENES: "Compra local de inventarios",
	IMPORTACION_BIENES: "Importacion de inventarios",
	COMPRA_ACTIVOS: "Adquisicion local de activos fijos",
	IMPORTACION_ACTIVOS: "Importacion de activos fijos",
	COMPRA_SERVICIOS: "Servicios recibidos",
	"225": "Nota de debito",
}
PAIS_LOCAL = "Dominican Republic"


def codigo_operacion(venta: bool, devolucion: bool, activo: bool, bien: bool, exterior: bool) -> str:
	"""Código propuesto según el tipo de documento y de artículo; el contador lo confirma."""
	if devolucion:
		return "131" if venta else "225"
	if venta:
		if activo:
			return "120" if exterior else VENTA_ACTIVOS
		if bien:
			return EXPORTACION if exterior else VENTA_BIENES
		return VENTA_SERVICIOS
	if activo:
		return IMPORTACION_ACTIVOS if exterior else COMPRA_ACTIVOS
	if bien:
		return IMPORTACION_BIENES if exterior else COMPRA_BIENES
	return COMPRA_SERVICIOS


def _lineas(company, desde, hasta, doctype: str, campo_parte: str, nombres: list[str]) -> list:
	factura = frappe.qb.DocType(doctype)
	linea = frappe.qb.DocType(f"{doctype} Item")
	articulo = frappe.qb.DocType("Item")
	return (
		frappe.qb.from_(linea)
		.join(factura)
		.on(linea.parent == factura.name)
		.left_join(articulo)
		.on(linea.item_code == articulo.name)
		.select(
			factura[campo_parte],
			factura.currency,
			factura.is_return,
			IfNull(factura.rd_tipo_comprobante, ""),
			IfNull(articulo.is_fixed_asset, 0),
			IfNull(articulo.is_stock_item, 0),
			Sum(linea.net_amount),
			Sum(linea.base_net_amount),
		)
		.where(
			(factura.company == company)
			& (factura.docstatus == 1)
			& (factura[campo_parte].isin(nombres))
			& (factura.posting_date[getdate(desde) : getdate(hasta)])
		)
		.groupby(
			factura[campo_parte],
			factura.currency,
			factura.is_return,
			factura.rd_tipo_comprobante,
			articulo.is_fixed_asset,
			articulo.is_stock_item,
		)
		.run()
	)


def hoja_detalle(company: str, desde, hasta) -> dict:
	"""Filas de las pestañas Empresas y Operaciones de la Hoja de Detalle de la DIOR (versión 6).

	Operaciones agrupadas por relacionado, código de operación y moneda, sin ITBIS y en positivo (las
	notas de crédito y débito van con su propio código). Los préstamos y otros asientos no se incluyen:
	su código (309, 401...) depende del contrato."""
	partes = relacionados()
	operaciones, contrapartes = {}, set()
	for doctype, parte, campo in (
		("Sales Invoice", "Customer", "customer"),
		("Purchase Invoice", "Supplier", "supplier"),
	):
		if not partes[parte]:
			continue
		venta = parte == "Customer"
		for nombre, moneda, devolucion, tipo, activo, bien, neto, base in _lineas(
			company, desde, hasta, doctype, campo, partes[parte]
		):
			if venta:
				exterior = tipo in ("B16", "E46")
			else:
				exterior = (
					frappe.get_cached_value("Supplier", nombre, "country") or PAIS_LOCAL
				) != PAIS_LOCAL
			codigo = codigo_operacion(venta, bool(devolucion), bool(activo), bool(bien), exterior)
			moneda = moneda if moneda in MONEDAS else "DOP"
			clave = (parte, nombre, codigo, moneda)
			fila = operaciones.setdefault(clave, {"original": 0.0, "base": 0.0})
			fila["original"] += abs(flt(base if moneda == "DOP" else neto))
			fila["base"] += abs(flt(base))
			contrapartes.add((parte, nombre))

	empresas = {}
	for parte, nombre in sorted(contrapartes):
		datos = _fila(parte, nombre, None)
		empresas[(parte, nombre)] = datos.nombre or nombre
	filas_empresas = [_fila_empresa(parte, nombre, empresas[(parte, nombre)]) for parte, nombre in empresas]
	filas_operaciones = []
	for (parte, nombre, codigo, moneda), m in sorted(
		operaciones.items(), key=lambda x: (empresas[x[0][:2]], x[0][2])
	):
		tasa = flt(m["base"] / m["original"], 4) if m["original"] else 1
		filas_operaciones.append(
			[
				empresas[(parte, nombre)],
				codigo,
				DESCRIPCIONES[codigo],
				flt(m["original"], 4),
				moneda,
				1.0 if moneda == "DOP" else tasa,
				flt(m["base"], 4),
				None,
				None,
				None,
				"No",
				None,
				None,
			]
		)
	return {"empresas": filas_empresas, "operaciones": filas_operaciones}


def _fila_empresa(parte: str, nombre: str, razon_social: str) -> list:
	from frappe.contacts.doctype.address.address import get_default_address

	tax_id, supuesto = frappe.db.get_value(parte, nombre, ["tax_id", "rd_supuesto_vinculacion"])
	direccion = ""
	nombre_direccion = get_default_address(parte, nombre)
	if nombre_direccion:
		linea, ciudad = frappe.db.get_value("Address", nombre_direccion, ["address_line1", "city"])
		direccion = ", ".join(x for x in (linea, ciudad) if x)
	return [
		razon_social,
		"".join(c for c in (tax_id or "") if c.isalnum()),
		None,
		None,
		None,
		direccion,
		(supuesto or "").split(" - ")[0] or None,
	]


@frappe.whitelist()
def descargar_hoja_detalle(company: str, desde: str | None = None, hasta: str | None = None):
	"""Excel con las pestañas Empresas y Operaciones para copiar y pegar en la DIOR de la Oficina Virtual."""
	from io import BytesIO

	from openpyxl import Workbook

	from erpnext_rd.dgii_reportes.formatos import ROLES

	frappe.only_for(ROLES)
	frappe.has_permission("Company", doc=company, throw=True)
	from erpnext_rd.dgii_reportes.report.operaciones_relacionadas_dior.operaciones_relacionadas_dior import (
		periodo,
	)

	desde, hasta = periodo(frappe._dict(company=company, desde=desde, hasta=hasta))
	datos = hoja_detalle(company, desde, hasta)
	libro = Workbook()
	for i, (titulo, columnas, filas) in enumerate(
		(
			("Empresas", COLUMNAS_EMPRESAS, datos["empresas"]),
			("Operaciones", COLUMNAS_OPERACIONES, datos["operaciones"]),
		)
	):
		hoja = libro.active if i == 0 else libro.create_sheet()
		hoja.title = titulo
		hoja.append(list(columnas))
		for fila in filas:
			hoja.append(fila)
	salida = BytesIO()
	libro.save(salida)
	frappe.response["filename"] = f"DIOR_Hoja_Detalle_{getdate(hasta).year}.xlsx"
	frappe.response["filecontent"] = salida.getvalue()
	frappe.response["type"] = "binary"
