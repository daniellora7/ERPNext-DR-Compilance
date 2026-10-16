"""Emisión de un e-CF: generar, firmar, validar contra el XSD, guardar y (si está habilitado) enviar.

- `emitir(doctype, name)`: desde el botón de la factura o en segundo plano al aprobarla (si el emisor
  tiene «Emitir al aprobar la factura»). Deja un *Envio ECF* con el XML firmado (archivo privado), el
  código de seguridad, el trackId y la respuesta de la DGII, y pone el código y la fecha de firma en la
  factura (los usa el QR del formato de impresión).
- Facturas de consumo (E32) menores al monto del emisor: además del e-CF se arma, firma y envía el
  resumen (RFCE), que la DGII responde en el momento.
- `consultar_pendientes`: tarea programada que pregunta a la DGII por los envíos «En proceso».
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from erpnext_rd.ecf import datos, esquemas, firma
from erpnext_rd.ecf.cliente import ClienteDGII, ErrorDGII

EMISOR = "Emisor ECF"
ENVIO = "Envio ECF"
DOCTYPES = ("Sales Invoice", "Purchase Invoice")
ESTADOS_FINALES = ("Aceptado", "Aceptado condicional", "Rechazado")


def estado(valor) -> str:
	"""Estado de la DGII (con cualquier mayúscula) en los términos del registro; si no es final, «En proceso»."""
	texto = " ".join(str(valor or "").split()).lower()
	return next((e for e in ESTADOS_FINALES if e.lower() == texto), "En proceso")


def _emisor(company: str):
	if not frappe.db.exists(EMISOR, company):
		frappe.throw(_("Configure el emisor e-CF de {0} (certificado digital).").format(company))
	return frappe.get_doc(EMISOR, company)


def _guardar_xml(envio, nombre: str, contenido: bytes) -> str:
	archivo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": nombre,
			"content": contenido,
			"is_private": 1,
			"attached_to_doctype": ENVIO,
			"attached_to_name": envio.name,
			"attached_to_field": "xml",
		}
	).insert(ignore_permissions=True)
	return archivo.file_url


def _mensajes(respuesta: dict) -> str:
	lista = respuesta.get("mensajes") or []
	if isinstance(lista, list):
		return "\n".join(str(m.get("valor") if isinstance(m, dict) else m) for m in lista if m)
	return str(respuesta.get("mensaje") or "")


@frappe.whitelist()
def emitir(doctype: str, name: str, enviar: int | None = None) -> str:
	"""Genera, firma y (según el emisor) envía el e-CF de la factura. Devuelve el Envio ECF."""
	if doctype not in DOCTYPES:
		frappe.throw(_("Tipo de documento no válido para e-CF: {0}").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Apruebe la factura antes de emitir el e-CF."))
	emisor = _emisor(doc.company)
	tipo = datos.tipo_ecf(doc)
	llave, certificado = emisor.cargar()

	fecha_firma = now_datetime()
	contenido = datos.datos_ecf(doc, fecha_firma)
	firmado = firma.firmar(esquemas.construir(tipo, contenido), llave, certificado)
	esquemas.validar(tipo, firmado)
	codigo = firma.codigo_seguridad(firmado)
	if doc.meta.has_field("rd_codigo_seguridad"):
		doc.db_set({"rd_codigo_seguridad": codigo, "rd_fecha_firma": fecha_firma})

	rnc = contenido["Encabezado"]["Emisor"]["RNCEmisor"]
	envio = frappe.get_doc(
		{
			"doctype": ENVIO,
			"company": doc.company,
			"tipo_documento": doctype,
			"documento": name,
			"encf": doc.rd_ncf,
			"tipo_ecf": f"E{tipo}",
			"ambiente": frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF",
			"estado": "Firmado",
			"codigo_seguridad": codigo,
			"fecha_firma": fecha_firma,
		}
	).insert(ignore_permissions=True)
	envio.db_set("xml", _guardar_xml(envio, f"{rnc}{doc.rd_ncf}.xml", firmado))

	if enviar if enviar is not None else emisor.habilitado:
		cliente = ClienteDGII(rnc, llave, certificado, envio.ambiente)
		try:
			if tipo == 32 and flt(doc.grand_total) < flt(emisor.monto_rfce):
				rfce = firma.firmar(
					esquemas.construir("RFCE", datos.datos_rfce(contenido, codigo)), llave, certificado
				)
				esquemas.validar("RFCE", rfce)
				respuesta = cliente.enviar_rfce(rfce, doc.rd_ncf)
				envio.update({"es_rfce": 1, "estado": estado(respuesta.get("estado"))})
			else:
				respuesta = cliente.enviar_ecf(firmado, doc.rd_ncf)
				envio.update({"track_id": respuesta.get("trackId"), "estado": "En proceso"})
				if respuesta.get("error"):
					envio.estado = "Error"
			envio.update(
				{
					"respuesta": json.dumps(respuesta, ensure_ascii=False, indent=1),
					"mensajes": _mensajes(respuesta),
				}
			)
		except (ErrorDGII, OSError) as error:
			envio.update({"estado": "Error", "mensajes": str(error)})
		envio.save(ignore_permissions=True)
	return envio.name


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


def consultar_pendientes():
	"""Tarea programada: actualiza los envíos «En proceso» con el resultado de la DGII."""
	for envio in frappe.get_all(
		ENVIO, filters={"estado": "En proceso", "track_id": ("is", "set")}, pluck="name"
	):
		doc = frappe.get_doc(ENVIO, envio)
		try:
			emisor = _emisor(doc.company)
			llave, certificado = emisor.cargar()
			rnc = frappe.get_cached_value("Company", doc.company, "tax_id")
			respuesta = ClienteDGII(rnc, llave, certificado, doc.ambiente).consultar_resultado(doc.track_id)
		except Exception as error:
			doc.add_comment("Comment", _("No se pudo consultar la DGII: {0}").format(error))
			continue
		doc.estado = estado(respuesta.get("estado"))
		doc.update(
			{
				"respuesta": json.dumps(respuesta, ensure_ascii=False, indent=1),
				"mensajes": _mensajes(respuesta),
			}
		)
		doc.save(ignore_permissions=True)
