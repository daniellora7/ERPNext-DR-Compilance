"""La empresa como compradora: recepción de e-CF de proveedores y aprobación comercial.

- `recibir_ecf`: lo llama el servicio público de recepción (`receptor.py`) cuando un proveedor entrega
  un e-CF. Revisa la firma, el esquema, que el comprador sea una empresa del sitio y que no esté
  repetido; lo registra en *ECF Recibido* y responde el acuse de recibo (ARECF) firmado.
- `aprobar`: botones Aprobar / Rechazar del e-CF recibido. Firma la aprobación comercial (ACECF) y la
  envía a la DGII y al emisor (su URL de aprobación, del directorio de la DGII).
- `recibir_aprobacion`: un cliente aprueba o rechaza un e-CF que emitimos; queda en su *Envio ECF*.
- `vincular_factura`: al aprobar una factura de compra con el e-NCF de un e-CF recibido, se enlazan.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime
from lxml import etree

from erpnext_rd.captura_compras import convertir
from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.ecf import datos, esquemas, firma
from erpnext_rd.ecf.cliente import ClienteDGII, ClienteReceptor, ErrorDGII
from erpnext_rd.ecf.emision import (
	EMISOR,
	ENVIO,
	MOTIVOS_NO_RECIBIDO,
	emisor_de,
	guardar_xml,
	mensajes,
	rnc_empresa,
)

RECIBIDO = "ECF Recibido"
TIPOS = (31, 32, 33, 34, 41, 43, 44, 45, 46, 47)
RECIBIDO_OK, NO_RECIBIDO = 0, 1
ESPECIFICACION, FIRMA, DUPLICADO, RNC_NO_CORRESPONDE = 1, 2, 3, 4
APROBADO, RECHAZADO = 1, 2


class ErrorRecepcion(Exception):
	"""Lo recibido no se puede ni acusar (no es un e-CF, falta el RNC): el servicio responde 400."""


def _empresa_por_rnc(rnc: str | None) -> str | None:
	if not rnc:
		return None
	for empresa in frappe.get_all("Company", filters={"tax_id": rnc}, pluck="name"):
		if es_empresa_rd(empresa) and frappe.db.exists(EMISOR, empresa):
			return empresa
	return None


def _emisor_para(rnc_comprador: str | None):
	"""(empresa, emisor) del comprador. Si el RNC no es de ninguna empresa del sitio, el acuse de
	«RNC comprador no corresponde» lo firma el primer emisor con certificado."""
	if empresa := _empresa_por_rnc(rnc_comprador):
		return empresa, emisor_de(empresa)
	otros = frappe.get_all(EMISOR, filters={"certificado": ("is", "set")}, pluck="name", limit=1)
	if not otros:
		raise ErrorRecepcion(_("Ninguna empresa del sitio tiene certificado para responder"))
	return None, frappe.get_doc(EMISOR, otros[0])


def _fecha(texto: str | None):
	try:
		dia, mes, anio = (texto or "").split("-")
		return getdate(f"{anio}-{mes}-{dia}")
	except ValueError:
		return None


def _leer_ecf(xml: bytes):
	"""(raíz, RNC emisor, RNC comprador, e-NCF, tipo) del e-CF."""
	try:
		raiz = firma.leer(xml)
	except etree.XMLSyntaxError as error:
		raise ErrorRecepcion(_("El archivo no es un XML válido: {0}").format(str(error))) from error
	if raiz.tag != "ECF":
		raise ErrorRecepcion(_("El documento no es un e-CF"))
	id_doc = "Encabezado/IdDoc/"
	rnc_emisor = datos._rnc(raiz.findtext("Encabezado/Emisor/RNCEmisor"))
	rnc_comprador = datos._rnc(raiz.findtext("Encabezado/Comprador/RNCComprador"))
	encf = (raiz.findtext(id_doc + "eNCF") or "").strip()
	if not (rnc_emisor and rnc_comprador and encf):
		raise ErrorRecepcion(_("Al e-CF le falta el RNC del emisor, el del comprador o el e-NCF"))
	return raiz, rnc_emisor, rnc_comprador, encf, cint(raiz.findtext(id_doc + "TipoeCF"))


def _motivo(xml: bytes, empresa: str | None, rnc_emisor: str, encf: str, tipo: int) -> int | None:
	"""Código del motivo de no recibido, o None si el e-CF se recibe."""
	if not firma.verificar(xml):
		return FIRMA
	if tipo not in TIPOS or esquemas.errores(tipo, xml):
		return ESPECIFICACION
	if not empresa:
		return RNC_NO_CORRESPONDE
	if frappe.db.exists(
		RECIBIDO, {"company": empresa, "rnc_emisor": rnc_emisor, "encf": encf, "estado": "Recibido"}
	):
		return DUPLICADO
	return None


def recibir_ecf(xml: bytes) -> bytes:
	"""Registra el e-CF de un proveedor y devuelve el acuse de recibo (ARECF) firmado."""
	raiz, rnc_emisor, rnc_comprador, encf, tipo = _leer_ecf(xml)
	empresa, emisor = _emisor_para(rnc_comprador)
	motivo = _motivo(xml, empresa, rnc_emisor, encf, tipo)

	ahora = now_datetime()
	llave, certificado = emisor.cargar()
	acuse = firma.firmar(
		esquemas.construir(
			"ARECF",
			{
				"DetalleAcusedeRecibo": {
					"Version": datos.VERSION,
					"RNCEmisor": rnc_emisor,
					"RNCComprador": rnc_comprador,
					"eNCF": encf,
					"Estado": NO_RECIBIDO if motivo else RECIBIDO_OK,
					"CodigoMotivoNoRecibido": motivo,
					"FechaHoraAcuseRecibo": datos.fecha_hora(ahora),
				}
			},
		),
		llave,
		certificado,
	)
	if empresa and motivo != DUPLICADO:
		_registrar(empresa, raiz, xml, acuse, motivo, ahora)
	return acuse


@frappe.whitelist(methods=["POST"])
def cargar_xml(file_url: str) -> str:
	"""Carga a mano el XML de un e-CF que el proveedor envió por correo. Pasa por las mismas
	validaciones que la recepción, pero no se responde acuse de recibo."""
	frappe.has_permission(RECIBIDO, "create", throw=True)
	from erpnext_rd.ecf.emision import leer_xml

	xml = leer_xml(file_url)
	try:
		raiz, rnc_emisor, rnc_comprador, encf, tipo = _leer_ecf(xml)
	except ErrorRecepcion as error:
		frappe.throw(str(error))
	empresa = next(
		(
			e
			for e in frappe.get_all("Company", filters={"tax_id": rnc_comprador}, pluck="name")
			if es_empresa_rd(e)
		),
		None,
	)
	if motivo := _motivo(xml, empresa, rnc_emisor, encf, tipo):
		frappe.throw(_("El e-CF no se puede registrar: {0}").format(_(MOTIVOS_NO_RECIBIDO.get(motivo))))
	frappe.has_permission("Company", doc=empresa, throw=True)
	return _registrar(empresa, raiz, xml, None, None, now_datetime(), origen="Carga manual").name


def _registrar(
	empresa: str,
	raiz,
	xml: bytes,
	acuse: bytes | None,
	motivo: int | None,
	ahora,
	origen: str = "Recepción electrónica",
):
	rnc_emisor = datos._rnc(raiz.findtext("Encabezado/Emisor/RNCEmisor"))
	encf = raiz.findtext("Encabezado/IdDoc/eNCF").strip()
	proveedor = frappe.db.get_value("Supplier", {"tax_id": rnc_emisor}, "name")
	doc = frappe.get_doc(
		{
			"doctype": RECIBIDO,
			"company": empresa,
			"encf": encf,
			"tipo_ecf": f"E{raiz.findtext('Encabezado/IdDoc/TipoeCF')}",
			"fecha_emision": _fecha(raiz.findtext("Encabezado/Emisor/FechaEmision")),
			"monto_total": flt(raiz.findtext("Encabezado/Totales/MontoTotal")),
			"total_itbis": flt(raiz.findtext("Encabezado/Totales/TotalITBIS")),
			"rnc_emisor": rnc_emisor,
			"razon_social_emisor": raiz.findtext("Encabezado/Emisor/RazonSocialEmisor"),
			"proveedor": proveedor,
			"factura_compra": frappe.db.get_value(
				"Purchase Invoice",
				{"company": empresa, "supplier": proveedor, "rd_ncf": encf, "docstatus": 1},
				"name",
			)
			if proveedor
			else None,
			"estado": "No recibido" if motivo else "Recibido",
			"motivo_no_recibido": MOTIVOS_NO_RECIBIDO.get(motivo) if motivo else None,
			"fecha_recepcion": ahora,
			"codigo_seguridad": None if motivo == FIRMA else firma.codigo_seguridad(xml),
			"aprobacion": "Pendiente",
			"origen": origen,
			"estado_conversion": "Ignorado" if motivo else "Pendiente",
		}
	)
	if not motivo:
		convertir.leer(doc, raiz)
	doc.insert(ignore_permissions=True)
	doc.xml = guardar_xml(RECIBIDO, doc.name, "xml", f"{rnc_emisor}{encf}.xml", xml)
	if acuse:
		guardar_xml(RECIBIDO, doc.name, "acuse", f"{rnc_emisor}{encf}_ARECF.xml", acuse)
	if not doc.factura_compra:
		convertir.al_registrar(doc)
	return doc


# ---------------------------------------------------------------- aprobación comercial (compradora)


@frappe.whitelist(methods=["POST"])
def aprobar(name: str, aprobado: int = 1, motivo: str | None = None) -> str:
	"""Aprueba o rechaza un e-CF recibido: firma la ACECF y la envía a la DGII y al emisor."""
	doc = frappe.get_doc(RECIBIDO, name)
	doc.check_permission("write")
	return decidir(doc, aprobado, motivo)


def decidir(doc, aprobado: int = 1, motivo: str | None = None) -> str:
	if doc.estado != "Recibido":
		frappe.throw(_("Solo se aprueban o rechazan los e-CF recibidos."))
	if doc.aprobacion != "Pendiente":
		frappe.throw(_("Este e-CF ya fue {0}.").format(_(doc.aprobacion).lower()))
	aprobado = cint(aprobado)
	motivo = " ".join((motivo or "").split())[:250]
	if not aprobado and not motivo:
		frappe.throw(_("Indique el motivo del rechazo."))

	emisor = emisor_de(doc.company)
	llave, certificado = emisor.cargar()
	ahora = now_datetime()
	acecf = firma.firmar(
		esquemas.construir(
			"ACECF",
			{
				"DetalleAprobacionComercial": {
					"Version": datos.VERSION,
					"RNCEmisor": doc.rnc_emisor,
					"eNCF": doc.encf,
					"FechaEmision": datos.fecha(doc.fecha_emision),
					"MontoTotal": datos.monto(doc.monto_total),
					"RNCComprador": rnc_empresa(doc.company),
					"Estado": APROBADO if aprobado else RECHAZADO,
					"DetalleMotivoRechazo": None if aprobado else motivo,
					"FechaHoraAprobacionComercial": datos.fecha_hora(ahora),
				}
			},
		),
		llave,
		certificado,
	)
	esquemas.validar("ACECF", acecf)
	doc.update(
		{
			"aprobacion": "Aprobado" if aprobado else "Rechazado",
			"motivo_rechazo": None if aprobado else motivo,
			"fecha_aprobacion": ahora,
			"envio_aprobacion": "Firmada",
		}
	)
	doc.xml_aprobacion = guardar_xml(
		RECIBIDO, doc.name, "xml_aprobacion", f"{rnc_empresa(doc.company)}{doc.encf}_ACECF.xml", acecf
	)
	if emisor.habilitado:
		enviar_aprobacion(doc, emisor)
	doc.save(ignore_permissions=True)
	return doc.aprobacion


def enviar_aprobacion(doc, emisor=None, sesion=None):
	"""Envía la ACECF firmada a la DGII y al emisor del e-CF."""
	from erpnext_rd.ecf.emision import leer_xml

	emisor = emisor or emisor_de(doc.company)
	llave, certificado = emisor.cargar()
	acecf = leer_xml(doc.xml_aprobacion)
	nombre = f"{rnc_empresa(doc.company)}{doc.encf}.xml"
	cliente = ClienteDGII(rnc_empresa(doc.company), llave, certificado, sesion=sesion)
	try:
		respuesta = cliente.enviar_aprobacion(acecf, nombre)
		notas = [mensajes(respuesta) or _("La DGII recibió la aprobación comercial.")]
		urls = cliente.directorio(doc.rnc_emisor)
		if urls:
			ClienteReceptor(urls, llave, certificado, sesion=sesion).enviar_aprobacion(acecf, nombre)
			notas.append(_("El emisor recibió la aprobación comercial."))
		else:
			notas.append(_("El emisor no está en el directorio de receptores electrónicos de la DGII."))
		doc.update({"envio_aprobacion": "Enviada", "mensajes": "\n".join(notas)})
	except (ErrorDGII, OSError) as error:
		doc.update({"envio_aprobacion": "Error", "mensajes": str(error)})
	return doc


@frappe.whitelist(methods=["POST"])
def reenviar_aprobacion(name: str) -> str:
	doc = frappe.get_doc(RECIBIDO, name)
	doc.check_permission("write")
	if not doc.xml_aprobacion:
		frappe.throw(_("Primero apruebe o rechace el e-CF."))
	enviar_aprobacion(doc)
	doc.save(ignore_permissions=True)
	return doc.envio_aprobacion


# ---------------------------------------------------------------- aprobación comercial (emisora)


def recibir_aprobacion(xml: bytes):
	"""Un cliente aprueba o rechaza un e-CF que emitimos: queda en su Envio ECF."""
	try:
		raiz = firma.leer(xml)
	except etree.XMLSyntaxError as error:
		raise ErrorRecepcion(_("El archivo no es un XML válido: {0}").format(str(error))) from error
	if raiz.tag != "ACECF":
		raise ErrorRecepcion(_("El documento no es una aprobación comercial"))
	if not firma.verificar(xml):
		raise ErrorRecepcion(_("La firma de la aprobación comercial no es válida"))
	if fallas := esquemas.errores("ACECF", xml):
		raise ErrorRecepcion(_("La aprobación comercial no cumple el esquema: {0}").format(fallas[0]))

	detalle = "DetalleAprobacionComercial/"
	empresa = _empresa_por_rnc(datos._rnc(raiz.findtext(detalle + "RNCEmisor")))
	encf = raiz.findtext(detalle + "eNCF").strip()
	envio = empresa and frappe.db.get_value(
		ENVIO, {"company": empresa, "encf": encf}, "name", order_by="creation desc"
	)
	if not envio:
		raise ErrorRecepcion(_("No hay un e-CF {0} emitido por ese RNC").format(encf))

	doc = frappe.get_doc(ENVIO, envio)
	aprobado = raiz.findtext(detalle + "Estado") == str(APROBADO)
	doc.update(
		{
			"aprobacion_comercial": "Aprobado" if aprobado else "Rechazado",
			"fecha_aprobacion_comercial": now_datetime(),
			"motivo_rechazo_comercial": None if aprobado else raiz.findtext(detalle + "DetalleMotivoRechazo"),
		}
	)
	rnc_comprador = datos._rnc(raiz.findtext(detalle + "RNCComprador"))
	doc.xml_aprobacion = guardar_xml(
		ENVIO, doc.name, "xml_aprobacion", f"{rnc_comprador}{encf}_ACECF.xml", xml
	)
	doc.save(ignore_permissions=True)
	return doc


def vincular_factura(doc, method=None):
	"""doc_events Purchase Invoice on_submit: enlaza el e-CF recibido con el mismo e-NCF y proveedor."""
	if not (doc.get("rd_ncf") or "").startswith("E"):
		return
	rnc = datos._rnc(frappe.db.get_value("Supplier", doc.supplier, "tax_id"))
	for fila in frappe.get_all(
		RECIBIDO,
		filters={"company": doc.company, "encf": doc.rd_ncf},
		or_filters={"proveedor": doc.supplier, "rnc_emisor": rnc or "-"},
		fields=["name", "factura_compra"],
	):
		if fila.factura_compra not in (None, "", doc.name):
			continue
		nombre = fila.name
		frappe.db.set_value(RECIBIDO, nombre, {"factura_compra": doc.name, "proveedor": doc.supplier})
		_aprobar_al_validar(nombre)


def _aprobar_al_validar(nombre: str):
	"""Si la empresa lo configuró, validar la factura aprueba comercialmente el e-CF (ACECF)."""
	recibido = frappe.db.get_value(RECIBIDO, nombre, ["company", "estado", "aprobacion"], as_dict=True)
	if recibido.estado != "Recibido" or recibido.aprobacion != "Pendiente":
		return
	if not cint(frappe.db.get_value(convertir.CONFIG, recibido.company, "aprobar_al_validar")):
		return
	try:
		decidir(frappe.get_doc(RECIBIDO, nombre))
	except frappe.ValidationError as error:
		frappe.msgprint(
			_("La factura se validó, pero no se pudo aprobar el e-CF {0}: {1}").format(nombre, str(error)),
			indicator="orange",
		)


def desvincular_factura(doc, method=None):
	"""doc_events Purchase Invoice on_cancel / on_trash: el e-CF recibido vuelve a quedar sin factura."""
	for nombre in frappe.get_all(RECIBIDO, filters={"factura_compra": doc.name}, pluck="name"):
		frappe.db.set_value(RECIBIDO, nombre, {"factura_compra": None, "estado_conversion": "Pendiente"})
