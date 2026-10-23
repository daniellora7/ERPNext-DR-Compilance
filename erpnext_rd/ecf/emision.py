"""Emisión de un e-CF: generar, firmar, validar contra el XSD, guardar y (si está habilitado) enviar.

- `emitir(doctype, name)`: desde el botón de la factura o en segundo plano al aprobarla (si el emisor
  tiene «Emitir al aprobar la factura»). Deja un *Envio ECF* con el XML firmado (archivo privado), el
  código de seguridad, el trackId y la respuesta de la DGII, y pone el código y la fecha de firma en la
  factura (los usa el QR del formato de impresión).
- Facturas de consumo (E32) menores al monto del emisor: además del e-CF se arma, firma y envía el
  resumen (RFCE), que la DGII responde en el momento.
- Contingencia: si la DGII no responde (caída, 5xx, sin conexión) el e-CF ya firmado es válido y queda
  «En contingencia»; `reintentar_contingencia` lo reenvía, cada vez más espaciado.
- `consultar_pendientes`: tarea programada que pregunta a la DGII por los envíos «En proceso».
- `entregar_a_compradores`: los e-CF aceptados se entregan al comprador si es receptor electrónico
  (directorio de la DGII); su acuse de recibo (ARECF) queda en el envío.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime

from erpnext_rd.ecf import datos, esquemas, firma
from erpnext_rd.ecf.cliente import ClienteDGII, ClienteReceptor, ErrorDGII

EMISOR = "Emisor ECF"
ENVIO = "Envio ECF"
DOCTYPES = ("Sales Invoice", "Purchase Invoice")
ESTADOS_FINALES = ("Aceptado", "Aceptado condicional", "Rechazado")
ACEPTADOS = ("Aceptado", "Aceptado condicional")
CONTINGENCIA = "Contingencia"
# Reintentos en contingencia: 15 min, 30, 1 h, 2 h y luego cada 4 h
MINUTOS_REINTENTO, MAXIMO_MINUTOS = 15, 240
# Tipos con un comprador contribuyente al que se entrega el e-CF (E32 consumo y E46 exportación no)
TIPOS_CON_COMPRADOR = ("E31", "E33", "E34", "E44", "E45")
INTENTOS_ENTREGA = 5
MOTIVOS_NO_RECIBIDO = {
	1: "Error de especificación",
	2: "Error de firma digital",
	3: "Envío duplicado",
	4: "RNC comprador no corresponde",
}


def estado(valor) -> str:
	"""Estado de la DGII (con cualquier mayúscula) en los términos del registro; si no es final, «En proceso»."""
	texto = " ".join(str(valor or "").split()).lower()
	return next((e for e in ESTADOS_FINALES if e.lower() == texto), "En proceso")


def emisor_de(company: str):
	if not frappe.db.exists(EMISOR, company):
		frappe.throw(_("Configure el emisor e-CF de {0} (certificado digital).").format(company))
	return frappe.get_doc(EMISOR, company)


def rnc_empresa(company: str) -> str:
	return datos._rnc(frappe.get_cached_value("Company", company, "tax_id"))


def guardar_xml(doctype: str, name: str, campo: str, nombre: str, contenido: bytes) -> str:
	"""Guarda el XML como archivo privado del documento y lo pone en el campo."""
	archivo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": nombre,
			"content": contenido,
			"is_private": 1,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
			"attached_to_field": campo,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(doctype, name, campo, archivo.file_url, update_modified=False)
	return archivo.file_url


def leer_xml(file_url: str) -> bytes:
	contenido = frappe.get_doc("File", {"file_url": file_url}).get_content()
	return contenido.encode("utf-8") if isinstance(contenido, str) else contenido


def mensajes(respuesta) -> str:
	if not isinstance(respuesta, dict):
		return ""
	lista = respuesta.get("mensajes") or []
	if isinstance(lista, list):
		return "\n".join(str(m.get("valor") if isinstance(m, dict) else m) for m in lista if m)
	return str(respuesta.get("mensaje") or "")


@frappe.whitelist(methods=["POST"])
def emitir(doctype: str, name: str, enviar: int | None = None) -> str:
	"""Genera, firma y (según el emisor) envía el e-CF de la factura. Devuelve el Envio ECF."""
	if doctype not in DOCTYPES:
		frappe.throw(_("Tipo de documento no válido para e-CF: {0}").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Apruebe la factura antes de emitir el e-CF."))
	emisor = emisor_de(doc.company)
	tipo = datos.tipo_ecf(doc)

	fecha_firma = now_datetime()
	contenido = datos.datos_ecf(doc, fecha_firma)
	envio = registrar(
		emisor,
		tipo,
		contenido,
		{"tipo_documento": doctype, "documento": name, "fecha_firma": fecha_firma},
		es_rfce=tipo == 32 and flt(doc.grand_total) < flt(emisor.monto_rfce),
	)
	if doc.meta.has_field("rd_codigo_seguridad"):
		doc.db_set({"rd_codigo_seguridad": envio.codigo_seguridad, "rd_fecha_firma": fecha_firma})

	if enviar if enviar is not None else emisor.habilitado:
		enviar_a_dgii(envio, emisor)
	return envio.name


def registrar(emisor, tipo, contenido: dict, campos: dict, es_rfce: bool = False):
	"""Arma, firma y valida el e-CF (y su resumen RFCE si corresponde) y deja el Envio ECF «Firmado»."""
	llave, certificado = emisor.cargar()
	firmado = firma.firmar(esquemas.construir(tipo, contenido), llave, certificado)
	esquemas.validar(tipo, firmado)
	codigo = firma.codigo_seguridad(firmado)
	encf = contenido["Encabezado"]["IdDoc"]["eNCF"]
	rnc = contenido["Encabezado"]["Emisor"]["RNCEmisor"]

	envio = frappe.get_doc(
		{
			"doctype": ENVIO,
			"company": emisor.company,
			"encf": encf,
			"tipo_ecf": f"E{tipo}",
			"ambiente": frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF",
			"estado": "Firmado",
			"codigo_seguridad": codigo,
			"es_rfce": 1 if es_rfce else 0,
			**campos,
		}
	).insert(ignore_permissions=True)
	envio.xml = guardar_xml(ENVIO, envio.name, "xml", f"{rnc}{encf}.xml", firmado)
	if es_rfce:
		rfce = firma.firmar(
			esquemas.construir("RFCE", datos.datos_rfce(contenido, codigo)), llave, certificado
		)
		esquemas.validar("RFCE", rfce)
		envio.xml_rfce = guardar_xml(ENVIO, envio.name, "xml_rfce", f"{rnc}{encf}_RFCE.xml", rfce)
	return envio


def enviar_a_dgii(envio, emisor=None):
	"""Envía (o reenvía) el XML firmado del envío. Si la DGII no responde, queda en contingencia."""
	emisor = emisor or emisor_de(envio.company)
	llave, certificado = emisor.cargar()
	cliente = ClienteDGII(rnc_empresa(envio.company), llave, certificado, envio.ambiente)
	try:
		if envio.es_rfce:
			respuesta = cliente.enviar_rfce(leer_xml(envio.xml_rfce), envio.encf)
			envio.estado = estado(respuesta.get("estado"))
		else:
			respuesta = cliente.enviar_ecf(leer_xml(envio.xml), envio.encf)
			envio.track_id = respuesta.get("trackId")
			envio.estado = "Error" if respuesta.get("error") or not envio.track_id else "En proceso"
		envio.update(
			{
				"respuesta": json.dumps(respuesta, ensure_ascii=False, indent=1),
				"mensajes": mensajes(respuesta),
				"proximo_intento": None,
			}
		)
	except (ErrorDGII, OSError) as error:
		if isinstance(error, OSError) or error.sin_servicio:
			envio.intentos = cint(envio.intentos) + 1
			espera = min(MINUTOS_REINTENTO * 2 ** (envio.intentos - 1), MAXIMO_MINUTOS)
			envio.update(
				{
					"estado": CONTINGENCIA,
					"proximo_intento": add_to_date(now_datetime(), minutes=espera),
					"mensajes": _("La DGII no respondió; se reintenta solo. {0}").format(str(error)),
				}
			)
		else:
			envio.update({"estado": "Error", "mensajes": str(error), "proximo_intento": None})
	envio.save(ignore_permissions=True)
	return envio


@frappe.whitelist(methods=["POST"])
def reenviar(envio: str) -> str:
	"""Botón del Envio ECF: envía a la DGII un e-CF firmado, con error o en contingencia."""
	doc = frappe.get_doc(ENVIO, envio)
	doc.check_permission("write")
	if doc.estado not in ("Firmado", "Error", CONTINGENCIA):
		frappe.throw(_("Este e-CF ya fue recibido por la DGII ({0}).").format(doc.estado))
	return enviar_a_dgii(doc).estado


def al_aprobar(doc, method=None):
	"""doc_events on_submit: emite en segundo plano si el emisor lo tiene activado."""
	if not (doc.get("rd_tipo_comprobante") or "").startswith("E"):
		return
	emisor = frappe.db.get_value(EMISOR, doc.company, ["habilitado", "envio_automatico"], as_dict=True)
	if emisor and emisor.habilitado and emisor.envio_automatico:
		frappe.enqueue(
			"erpnext_rd.ecf.emision.emitir",
			queue="short",
			doctype=doc.doctype,
			name=doc.name,
			enqueue_after_commit=True,
		)


def _habilitado(company: str) -> bool:
	return bool(frappe.db.get_value(EMISOR, company, "habilitado"))


def reintentar_contingencia():
	"""Tarea programada: reenvía los e-CF en contingencia cuya hora de reintento llegó."""
	for nombre in frappe.get_all(
		ENVIO,
		filters={"estado": CONTINGENCIA, "proximo_intento": ("<=", now_datetime())},
		order_by="proximo_intento",
		pluck="name",
	):
		doc = frappe.get_doc(ENVIO, nombre)
		if not _habilitado(doc.company):
			continue
		try:
			enviar_a_dgii(doc)
		except Exception:
			doc.log_error(_("Reintento del e-CF en contingencia"))


def consultar_pendientes():
	"""Tarea programada: actualiza los envíos «En proceso» con el resultado de la DGII."""
	for envio in frappe.get_all(
		ENVIO, filters={"estado": "En proceso", "track_id": ("is", "set")}, pluck="name"
	):
		doc = frappe.get_doc(ENVIO, envio)
		try:
			llave, certificado = emisor_de(doc.company).cargar()
			respuesta = ClienteDGII(
				rnc_empresa(doc.company), llave, certificado, doc.ambiente
			).consultar_resultado(doc.track_id)
		except Exception as error:
			doc.add_comment("Comment", _("No se pudo consultar la DGII: {0}").format(str(error)))
			continue
		doc.estado = estado(respuesta.get("estado"))
		doc.update(
			{
				"respuesta": json.dumps(respuesta, ensure_ascii=False, indent=1),
				"mensajes": mensajes(respuesta),
			}
		)
		doc.save(ignore_permissions=True)


# ---------------------------------------------------------------- entrega al comprador


def entregar_al_comprador(envio, emisor=None, sesion=None):
	"""Entrega el e-CF aceptado al comprador si es receptor electrónico y guarda su acuse (ARECF)."""
	emisor = emisor or emisor_de(envio.company)
	llave, certificado = emisor.cargar()
	xml = leer_xml(envio.xml)
	rnc_comprador = datos._rnc(firma.leer(xml).findtext("Encabezado/Comprador/RNCComprador"))
	rnc = rnc_empresa(envio.company)
	try:
		urls = (
			ClienteDGII(rnc, llave, certificado, envio.ambiente, sesion=sesion).directorio(rnc_comprador)
			if rnc_comprador
			else None
		)
		if not urls:
			envio.estado_comprador = "No es receptor electrónico"
		else:
			acuse = ClienteReceptor(urls, llave, certificado, sesion=sesion).enviar_ecf(
				xml, f"{rnc}{envio.encf}.xml"
			)
			raiz = firma.leer(acuse)
			recibido = raiz.findtext("DetalleAcusedeRecibo/Estado") == "0"
			envio.estado_comprador = "Recibido" if recibido else "No recibido"
			if not recibido:
				motivo = cint(raiz.findtext("DetalleAcusedeRecibo/CodigoMotivoNoRecibido"))
				envio.add_comment(
					"Comment",
					_("El comprador no recibió el e-CF: {0}").format(
						_(MOTIVOS_NO_RECIBIDO.get(motivo, "")) or motivo
					),
				)
			envio.acuse_comprador = guardar_xml(
				ENVIO, envio.name, "acuse_comprador", f"{rnc_comprador}{envio.encf}_ARECF.xml", acuse
			)
	except (ErrorDGII, OSError, ValueError) as error:
		envio.intentos_comprador = cint(envio.intentos_comprador) + 1
		envio.estado_comprador = "Error"
		envio.add_comment("Comment", _("No se pudo entregar el e-CF al comprador: {0}").format(str(error)))
	envio.save(ignore_permissions=True)
	return envio


@frappe.whitelist(methods=["POST"])
def entregar(envio: str) -> str:
	"""Botón del Envio ECF: entrega (o vuelve a entregar) el e-CF aceptado al comprador."""
	doc = frappe.get_doc(ENVIO, envio)
	doc.check_permission("write")
	if doc.estado not in ACEPTADOS or doc.es_rfce or doc.tipo_ecf not in TIPOS_CON_COMPRADOR:
		frappe.throw(_("Solo se entregan al comprador los e-CF aceptados con comprador contribuyente."))
	return entregar_al_comprador(doc).estado_comprador


def entregar_a_compradores():
	"""Tarea programada: entrega a sus compradores los e-CF aceptados que faltan (con reintentos)."""
	for fila in frappe.get_all(
		ENVIO,
		filters={
			"estado": ("in", ACEPTADOS),
			"es_rfce": 0,
			"tipo_ecf": ("in", TIPOS_CON_COMPRADOR),
			"intentos_comprador": ("<", INTENTOS_ENTREGA),
		},
		fields=["name", "estado_comprador"],
	):
		if fila.estado_comprador not in (None, "", "Pendiente", "Error"):
			continue
		doc = frappe.get_doc(ENVIO, fila.name)
		if not _habilitado(doc.company):
			continue
		try:
			entregar_al_comprador(doc)
		except Exception:
			doc.log_error(_("Entrega del e-CF al comprador"))
