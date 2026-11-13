"""Conservación de los e-CF.

Base: Guía para ser Emisor Electrónico (DGII, enero de 2025), «Conservar los e-CF conforme a lo
dispuesto en el Código Tributario» (art. 50, literal h). Lo firmado o recibido no se borra: ni el
registro ni sus XML. Un e-CF se corrige con una nota de crédito y una secuencia sin usar se anula con
la ANECF.

- *Envio ECF*: siempre (se crea ya firmado).
- *ECF Recibido*: si se recibió. Uno «No recibido» (firma o esquema inválido) no es un e-CF válido.
- *Anulacion ENCF*: desde que tiene la ANECF firmada.
"""

import frappe
from frappe import _

PROTEGIDOS = ("Envio ECF", "ECF Recibido", "Anulacion ENCF")


def protegido(doctype: str, name: str | None) -> bool:
	if doctype not in PROTEGIDOS or not name:
		return False
	if doctype == "Envio ECF":
		return bool(frappe.db.exists(doctype, name))
	if doctype == "ECF Recibido":
		return frappe.db.get_value(doctype, name, "estado") == "Recibido"
	return bool(frappe.db.get_value(doctype, name, "xml"))


def no_borrar(doc):
	"""on_trash de los DocTypes protegidos."""
	if protegido(doc.doctype, doc.name):
		frappe.throw(
			_("{0} {1} se conserva según el Código Tributario (art. 50): no se puede borrar.").format(
				_(doc.doctype), doc.name
			),
			title=_("e-CF que se conserva"),
		)


def proteger_archivo(doc, method=None):
	"""doc_events File on_trash: el XML de un e-CF protegido no se borra."""
	if protegido(doc.attached_to_doctype, doc.attached_to_name):
		frappe.throw(
			_("El archivo {0} es parte de {1} {2} y se conserva: no se puede borrar.").format(
				doc.file_name, _(doc.attached_to_doctype), doc.attached_to_name
			),
			title=_("e-CF que se conserva"),
		)
