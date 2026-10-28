"""Captura de compras: convierte un e-CF recibido de un proveedor en una Factura de Compra en borrador.

- `leer`: llena el detalle y los totales del *ECF Recibido* desde su XML.
- `desde_ecf`: trabajo en segundo plano que lanza la recepción (`recepcion._registrar`).
- `crear_factura`, `ignorar`: botones del *ECF Recibido*.
- `convertir`: busca o crea el proveedor, resuelve el artículo de cada línea (artículo del proveedor,
  regla de gasto o artículo genérico), pone el ITBIS y las retenciones del XML y deja la factura en
  borrador. Nunca la valida: lo que no cuadra queda en «Requiere revisión».
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, nowdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.ecf import firma
from erpnext_rd.ecf.emision import leer_xml

RECIBIDO = "ECF Recibido"
CONFIG = "Configuracion Captura Compras"
COMPRA = "Purchase Invoice"
# Tipos que se registran como factura de compra. E32 y E46 no dan crédito en compras y la factura
# de compra no tiene nota de débito (E33): esos se registran a mano.
TIPOS_COMPRA = ("E31", "E34", "E44", "E45")
NOTA_CREDITO = "E34"
INDICADORES = {1: "ITBIS 18%", 2: "ITBIS 16%", 3: "ITBIS 0%", 4: "Exento"}
TASAS = {1: 18, 2: 16}
TOTALES = "Encabezado/Totales/"


# ---------------------------------------------------------------- lectura del XML


def leer(doc, raiz=None):
	"""Detalle y totales del e-CF recibido, desde su XML."""
	if raiz is None:
		raiz = firma.leer(leer_xml(doc.xml))
	doc.set("detalle", [])
	for item in raiz.findall("DetallesItems/Item"):
		doc.append(
			"detalle",
			{
				"numero_linea": cint(item.findtext("NumeroLinea")),
				"codigo_proveedor": item.findtext("TablaCodigosItem/CodigosItem/CodigoItem"),
				"descripcion": (item.findtext("NombreItem") or "")[:140],
				"cantidad": flt(item.findtext("CantidadItem")),
				"unidad": item.findtext("UnidadMedida"),
				"precio": flt(item.findtext("PrecioUnitarioItem")),
				"descuento": flt(item.findtext("DescuentoMonto")),
				"monto": flt(item.findtext("MontoItem")),
				"indicador_facturacion": INDICADORES.get(cint(item.findtext("IndicadorFacturacion"))),
			},
		)

	def total(campo):
		return flt(raiz.findtext(TOTALES + campo))

	doc.update(
		{
			"monto_gravado_i1": total("MontoGravadoI1"),
			"monto_gravado_i2": total("MontoGravadoI2"),
			"monto_gravado_i3": total("MontoGravadoI3"),
			"monto_exento": total("MontoExento"),
			"itbis_i1": total("TotalITBIS1"),
			"itbis_i2": total("TotalITBIS2"),
			"itbis_retenido": total("TotalITBISRetenido"),
			"isr_retenido": total("TotalISRRetencion"),
			"otros_impuestos": total("MontoImpuestoAdicional"),
			"moneda": raiz.findtext("Encabezado/OtraMoneda/TipoMoneda"),
			"tasa_cambio": flt(raiz.findtext("Encabezado/OtraMoneda/TipoCambio")),
		}
	)
	return raiz


# ---------------------------------------------------------------- disparadores


def al_registrar(doc):
	"""Desde la recepción: convierte en segundo plano si la empresa lo configuró."""
	if doc.estado != "Recibido" or not es_empresa_rd(doc.company):
		return
	if not cint(frappe.db.get_value(CONFIG, doc.company, "crear_borrador_automatico")):
		return
	frappe.enqueue(
		"erpnext_rd.captura_compras.convertir.desde_ecf",
		queue="short",
		name=doc.name,
		enqueue_after_commit=True,
	)


def desde_ecf(name: str):
	"""Trabajo en segundo plano: un error queda en el e-CF recibido, no en el registro de errores."""
	frappe.db.savepoint("captura_compras")
	try:
		convertir(frappe.get_doc(RECIBIDO, name))
	except Exception as error:
		frappe.db.rollback(save_point="captura_compras")
		frappe.db.set_value(
			RECIBIDO, name, {"estado_conversion": "Error", "mensajes_conversion": str(error)[:1000]}
		)


@frappe.whitelist(methods=["POST"])
def crear_factura(name: str) -> str | None:
	"""Botón «Crear factura de compra» / «Reintentar»."""
	doc = frappe.get_doc(RECIBIDO, name)
	doc.check_permission("write")
	frappe.has_permission(COMPRA, "create", throw=True)
	return convertir(doc)


@frappe.whitelist(methods=["POST"])
def ignorar(name: str) -> str:
	"""Botón «Ignorar»: el e-CF no se registra como compra (gasto personal, duplicado en papel…)."""
	doc = frappe.get_doc(RECIBIDO, name)
	doc.check_permission("write")
	if doc.factura_compra:
		frappe.throw(_("El e-CF ya tiene la factura de compra {0}.").format(doc.factura_compra))
	doc.estado_conversion = "Ignorado"
	doc.save(ignore_permissions=True)
	return doc.estado_conversion


# ---------------------------------------------------------------- conversión


def convertir(doc) -> str | None:
	"""Crea la factura de compra en borrador del e-CF recibido y devuelve su nombre."""
	if not es_empresa_rd(doc.company):
		return None
	if doc.estado != "Recibido":
		frappe.throw(_("Solo se convierten los e-CF recibidos."))
	if doc.factura_compra:
		return doc.factura_compra
	if doc.tipo_ecf not in TIPOS_COMPRA:
		frappe.throw(
			_("Los e-CF {0} no se convierten en factura de compra: regístrela a mano.").format(doc.tipo_ecf)
		)
	if not frappe.db.exists(CONFIG, doc.company):
		frappe.throw(_("Falta la Configuración de captura de compras de la empresa {0}.").format(doc.company))
	config = frappe.get_cached_doc(CONFIG, doc.company)

	raiz = leer(doc)
	avisos = []
	proveedor = _proveedor(doc, config)
	if existente := frappe.db.get_value(
		COMPRA, {"company": doc.company, "supplier": proveedor, "rd_ncf": doc.encf, "docstatus": ("<", 2)}
	):
		avisos.append(_("Ya existía la factura de compra {0} con este e-NCF.").format(existente))
		return _enlazar(doc, proveedor, existente, avisos)

	factura = _factura(doc, raiz, proveedor, config, avisos)
	factura.insert(ignore_permissions=True)
	_cuadre(doc, factura, config, avisos)
	frappe.get_doc(
		{
			"doctype": "File",
			"file_url": doc.xml,
			"is_private": 1,
			"attached_to_doctype": COMPRA,
			"attached_to_name": factura.name,
		}
	).insert(ignore_permissions=True)
	if avisos:
		factura.add_comment("Comment", "<br>".join(avisos))
	return _enlazar(doc, proveedor, factura.name, avisos)


def _enlazar(doc, proveedor: str, factura: str, avisos: list[str]) -> str:
	doc.update(
		{
			"proveedor": proveedor,
			"factura_compra": factura,
			"estado_conversion": "Requiere revisión" if avisos else "Borrador creado",
			"mensajes_conversion": "\n".join(avisos) or None,
		}
	)
	doc.save(ignore_permissions=True)
	return factura


def _proveedor(doc, config) -> str:
	if proveedor := frappe.db.get_value("Supplier", {"tax_id": doc.rnc_emisor}, "name"):
		return proveedor
	if not cint(config.crear_proveedor):
		frappe.throw(_("No hay un proveedor con el RNC {0}.").format(doc.rnc_emisor))
	nombre = frappe.db.get_value("Contribuyente DGII", doc.rnc_emisor, "razon_social")
	return (
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": nombre or doc.razon_social_emisor or doc.rnc_emisor,
				"supplier_group": config.grupo_proveedor
				or frappe.db.get_single_value("Buying Settings", "supplier_group"),
				"tax_id": doc.rnc_emisor,
				"country": frappe.get_cached_value("Company", doc.company, "country"),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _factura(doc, raiz, proveedor: str, config, avisos: list[str]):
	devolucion = doc.tipo_ecf == NOTA_CREDITO
	signo = -1 if devolucion else 1
	modificado = (raiz.findtext("InformacionReferencia/NCFModificado") or "").strip() or None
	firmado = raiz.findtext("FechaHoraFirma")
	factura = frappe.get_doc(
		{
			"doctype": COMPRA,
			"company": doc.company,
			"supplier": proveedor,
			"posting_date": nowdate(),
			"bill_no": doc.encf,
			"bill_date": doc.fecha_emision,
			"rd_ncf": doc.encf,
			"rd_tipo_comprobante": doc.tipo_ecf,
			"rd_codigo_seguridad": doc.codigo_seguridad,
			"rd_fecha_firma": get_datetime(_fecha_hora(firmado)) if firmado else None,
			"rd_ncf_modificado": modificado,
			"is_return": cint(devolucion),
		}
	)
	if devolucion:
		factura.return_against = modificado and frappe.db.get_value(
			COMPRA, {"company": doc.company, "supplier": proveedor, "rd_ncf": modificado, "docstatus": 1}
		)
		if not factura.return_against:
			avisos.append(
				_("No se encontró la factura original {0} de la nota de crédito.").format(modificado)
			)

	incluye_itbis = cint(raiz.findtext("Encabezado/IdDoc/IndicadorMontoGravado"))
	tipo_606 = None
	for linea in doc.detalle:
		item, cuenta, centro, tipo = _resolver(linea, proveedor, config, avisos)
		tipo_606 = tipo_606 or tipo
		linea.update({"item": item, "cuenta_gasto": cuenta, "centro_costo": centro})
		monto = flt(linea.monto)
		indicador = next((k for k, v in INDICADORES.items() if v == linea.indicador_facturacion), 4)
		if incluye_itbis and indicador in TASAS:
			monto /= 1 + TASAS[indicador] / 100
		cantidad = flt(linea.cantidad) or 1
		factura.append(
			"items",
			{
				"item_code": item,
				"description": linea.descripcion,
				"qty": signo * cantidad,
				"rate": monto / cantidad,
				"expense_account": cuenta,
				"cost_center": centro,
			},
		)
	factura.rd_tipo_bienes_servicios = tipo_606

	for cuenta, monto, tipo, descripcion in (
		(config.cuenta_itbis, flt(doc.total_itbis), "Add", _("ITBIS facturado")),
		(config.cuenta_itbis_retenido, flt(doc.itbis_retenido), "Deduct", _("ITBIS retenido")),
		(config.cuenta_isr_retenido, flt(doc.isr_retenido), "Deduct", _("ISR retenido")),
	):
		if not monto:
			continue
		if not cuenta:
			avisos.append(_("Falta la cuenta de {0} en la configuración.").format(descripcion))
			continue
		factura.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": cuenta,
				"tax_amount": signo * monto,
				"add_deduct_tax": tipo,
				"category": "Total",
				"description": descripcion,
			},
		)
	if flt(doc.otros_impuestos):
		avisos.append(
			_("El e-CF trae otros impuestos por {0}: agréguelos a mano.").format(doc.otros_impuestos)
		)
	return factura


def _resolver(linea, proveedor: str, config, avisos: list[str]):
	"""(artículo, cuenta de gasto, centro de costo, tipo 606) de una línea del e-CF."""
	if linea.codigo_proveedor and (item := _item_del_proveedor(proveedor, linea.codigo_proveedor)):
		return item, None, None, None
	descripcion = (linea.descripcion or "").lower()
	for regla in config.reglas:
		if regla.proveedor not in (None, "", proveedor):
			continue
		if regla.contiene and regla.contiene.lower() not in descripcion:
			continue
		return (
			regla.item or config.item_generico,
			regla.cuenta_gasto or config.cuenta_gasto_defecto,
			regla.centro_costo or config.centro_costo_defecto,
			regla.rd_tipo_bienes_servicios,
		)
	if not config.item_generico:
		frappe.throw(_("Falta el artículo genérico en la Configuración de captura de compras."))
	avisos.append(
		_("Línea {0} ({1}): sin artículo del proveedor ni regla.").format(
			linea.numero_linea, linea.descripcion
		)
	)
	return config.item_generico, config.cuenta_gasto_defecto, config.centro_costo_defecto, None


def _item_del_proveedor(proveedor: str, codigo: str) -> str | None:
	tabla = frappe.qb.DocType("Item Supplier")
	fila = (
		frappe.qb.from_(tabla)
		.select(tabla.parent)
		.where((tabla.supplier == proveedor) & (tabla.supplier_part_no == codigo))
		.limit(1)
		.run()
	)
	return fila[0][0] if fila else None


def _cuadre(doc, factura, config, avisos: list[str]):
	# MontoTotal del e-CF no resta las retenciones; la factura sí
	total = abs(flt(factura.grand_total)) + abs(flt(factura.taxes_and_charges_deducted))
	if abs(total - flt(doc.monto_total)) > flt(config.tolerancia_redondeo):
		avisos.append(
			_("El total de la factura ({0}) no cuadra con el del e-CF ({1}).").format(total, doc.monto_total)
		)


def _fecha_hora(texto: str) -> str:
	"""dd-mm-aaaa hh:mm:ss del e-CF -> aaaa-mm-dd hh:mm:ss."""
	fecha, _sep, hora = texto.strip().partition(" ")
	dia, mes, anio = fecha.split("-")
	return f"{anio}-{mes}-{dia} {hora}"
