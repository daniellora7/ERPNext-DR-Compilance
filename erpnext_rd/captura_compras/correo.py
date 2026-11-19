"""e-CF que los proveedores envían por correo (plan de captura de compras, 1.4).

Cada empresa puede elegir en su *Configuracion Captura Compras* una *Email Account* de Frappe. Los
adjuntos `.xml` de los correos recibidos en esa cuenta se registran como *ECF Recibido* con las mismas
validaciones de «Cargar XML» (firma, certificado, XSD, comprador y duplicado), sin acuse de recibo. Como
en la carga manual, la verificación periódica con la DGII confirma después que el e-CF existe.

El resultado de cada adjunto queda como comentario en el correo.
"""

import frappe
from frappe import _

from erpnext_rd.ecf import recepcion

CONFIG = "Configuracion Captura Compras"
ORIGEN = "Correo electrónico"


def al_adjuntar(doc, method=None):
	"""doc_events File after_insert: encola los .xml adjuntos a un correo (sin consultas: se llama con
	cada archivo que se sube al sitio)."""
	if doc.attached_to_doctype != "Communication" or not doc.attached_to_name:
		return
	if not (doc.file_name or "").lower().endswith(".xml"):
		return
	frappe.enqueue(
		"erpnext_rd.captura_compras.correo.registrar",
		queue="short",
		enqueue_after_commit=True,
		archivo=doc.name,
	)


def registrar(archivo: str) -> str | None:
	"""Registra el adjunto como e-CF recibido. Devuelve el nombre del *ECF Recibido* o None."""
	adjunto = frappe.get_doc("File", archivo)
	correo = frappe.db.get_value(
		"Communication",
		adjunto.attached_to_name,
		["name", "email_account", "sent_or_received"],
		as_dict=True,
	)
	if not correo or correo.sent_or_received != "Received" or not correo.email_account:
		return None
	empresas = frappe.get_all(CONFIG, filters={"cuenta_correo": correo.email_account}, pluck="company")
	if not empresas:
		return None

	contenido = adjunto.get_content()
	xml = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
	try:
		empresa, raiz = recepcion.validar_archivo(xml, empresas)
	except frappe.ValidationError as error:
		frappe.clear_messages()
		_comentar(
			correo.name,
			_("El adjunto {0} no se registró como e-CF recibido: {1}").format(adjunto.file_name, str(error)),
		)
		return None

	doc = recepcion.registrar_archivo(empresa, raiz, xml, ORIGEN, comunicacion=correo.name)
	_comentar(
		correo.name,
		_("El adjunto {0} se registró como el e-CF recibido {1}.").format(adjunto.file_name, doc.name),
	)
	return doc.name


def _comentar(comunicacion: str, texto: str):
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Communication",
			"reference_name": comunicacion,
			"content": texto,
		}
	).insert(ignore_permissions=True)
