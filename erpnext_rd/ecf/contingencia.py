"""Contingencia de la facturación electrónica.

Base: Instructivo de Contingencia de Facturación Electrónica (DGII, octubre de 2026), Guía para ser
Emisor Electrónico (DGII, enero de 2025) y Decreto 587-24, art. 40 (citado por ambos). Los plazos van en
*Configuracion DGII*.

- **Falta de conexión.** El e-CF se firma igual y su *Envio ECF* queda «Contingencia» (ver
  `emision.enviar_a_dgii`). Hay que enviarlo a la DGII en `horas_contingencia_ecf` (72) horas.
  `vence_envio` da el límite y el monitor avisa. La representación impresa lleva la leyenda
  `LEYENDA_SIN_CONEXION`.
- **Imposibilidad de emitir e-CF.** La empresa declara la entrada y la salida en la Oficina Virtual
  y copia las fechas al *Emisor ECF*. Mientras dura, que no pasa de `dias_contingencia_ncf` (15) días,
  las ventas salen con comprobantes de la serie B (`permite_serie_b`). Después de la salida hay
  `dias_reemplazo_contingencia` (30) días para enviar a la DGII, y solo a la DGII, los e-CF que las
  reemplazan (`emitir_reemplazo`).
- **e-CF de reemplazo.** Es el mismo tipo en electrónico (B01 → E31, B02 → E32…), con un e-NCF nuevo y
  `InformacionReferencia` con el NCF de la serie B, su fecha y `CodigoModificacion` 4 («Reemplazo NCF
  emitido en contingencia», XSD de la DGII). El comprador sustenta su gasto con el comprobante de la
  serie B que recibió: el e-CF no se le entrega.
"""

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.utils import add_days, add_to_date, cint, date_diff, flt, get_datetime, getdate, now_datetime

from erpnext_rd.dgii_fiscal import isc, ncf
from erpnext_rd.ecf import datos, emision

CONFIG = "Configuracion DGII"
FACTURA = "Sales Invoice"
REEMPLAZO_CONTINGENCIA = 4
# Serie B que puede salir en contingencia → su e-CF de reemplazo. Las notas de crédito y débito de
# facturas de la serie B ya siguen en la serie B (perfil.validar_serie_de_venta).
EQUIVALENTES = {"B01": "E31", "B02": "E32", "B14": "E44", "B15": "E45", "B16": "E46"}
LEYENDA_SIN_CONEXION = (
	"e-CF emitido en modalidad de Contingencia, el cual podrá ser consultado para su validez fiscal, "
	"a partir de las setenta y dos (72) horas."
)


def _config(campo: str, defecto: int) -> int:
	return cint(frappe.db.get_single_value(CONFIG, campo)) or defecto


def horas_envio() -> int:
	return _config("horas_contingencia_ecf", 72)


def dias_maximos() -> int:
	return _config("dias_contingencia_ncf", 15)


def dias_reemplazo() -> int:
	return _config("dias_reemplazo_contingencia", 30)


def vence_envio(fecha_firma):
	"""Límite para enviar a la DGII un e-CF firmado sin conexión."""
	return add_to_date(get_datetime(fecha_firma), hours=horas_envio()) if fecha_firma else None


def declarada(company: str, fecha=None) -> frappe._dict | None:
	"""La contingencia del *Emisor ECF* que cubre la fecha, o None."""
	e = frappe.db.get_value(
		emision.EMISOR,
		company,
		["contingencia_desde", "contingencia_hasta", "contingencia_modalidad"],
		as_dict=True,
	)
	if not e or not e.contingencia_desde:
		return None
	fecha = getdate(fecha)
	if fecha < getdate(e.contingencia_desde) or (
		e.contingencia_hasta and fecha > getdate(e.contingencia_hasta)
	):
		return None
	return e


def permite_serie_b(doc, tipo) -> bool:
	"""Venta de un emisor electrónico con comprobante de la serie B: solo en una contingencia declarada,
	dentro de su plazo máximo y en los tipos que tienen e-CF de reemplazo. Marca la factura."""
	contingencia = declarada(doc.company, doc.posting_date)
	if not contingencia:
		return False
	if tipo.name not in EQUIVALENTES:
		frappe.throw(
			_("En contingencia solo se emiten {0}: {1} no tiene e-CF de reemplazo.").format(
				", ".join(EQUIVALENTES), tipo.name
			),
			title=_("Comprobante no permitido"),
		)
	dias = date_diff(doc.posting_date, contingencia.contingencia_desde) + 1
	if dias > dias_maximos():
		frappe.throw(
			_(
				"La contingencia empezó el {0} y no puede pasar de {1} días calendario (Decreto 587-24, "
				"art. 40). Declare la salida en la Oficina Virtual y emita e-CF."
			).format(frappe.format(contingencia.contingencia_desde, "Date"), dias_maximos()),
			title=_("Contingencia vencida"),
		)
	if getattr(doc, "meta", None) and doc.meta.has_field("rd_contingencia_ecf"):
		doc.rd_contingencia_ecf = 1
	return True


def al_cambiar_emisor(emisor):
	"""Emisor ECF on_update: con la salida de la contingencia, cada factura de la serie B que la
	contingencia cubre recibe el plazo para enviar su e-CF de reemplazo."""
	if not (emisor.contingencia_desde and emisor.contingencia_hasta):
		return
	plazo = add_days(emisor.contingencia_hasta, dias_reemplazo())
	si = DocType(FACTURA)
	(
		frappe.qb.update(si)
		.set(si.rd_plazo_reemplazo, plazo)
		.where(
			(si.company == emisor.company)
			& (si.docstatus == 1)
			& (si.rd_contingencia_ecf == 1)
			& (si.rd_encf_reemplazo.isnull() | (si.rd_encf_reemplazo == ""))
			& si.posting_date[emisor.contingencia_desde : emisor.contingencia_hasta]
		)
	).run()


def validar_emisor(emisor):
	"""Emisor ECF validate: fechas de la contingencia."""
	if emisor.contingencia_hasta and not emisor.contingencia_desde:
		frappe.throw(_("Indique la entrada en contingencia."))
	if not emisor.contingencia_desde:
		return
	if getdate(emisor.contingencia_desde) > getdate():
		frappe.throw(_("La entrada en contingencia no puede ser una fecha futura."))
	if emisor.contingencia_hasta and getdate(emisor.contingencia_hasta) < getdate(emisor.contingencia_desde):
		frappe.throw(_("La salida de contingencia no puede ser antes de la entrada."))
	fin = emisor.contingencia_hasta or getdate()
	if date_diff(fin, emisor.contingencia_desde) + 1 > dias_maximos():
		frappe.msgprint(
			_("La contingencia pasa de {0} días calendario (Decreto 587-24, art. 40).").format(
				dias_maximos()
			),
			indicator="orange",
			alert=True,
		)


def pendientes(company: str, limite: int = 50) -> list[dict]:
	"""Facturas de la serie B emitidas en contingencia sin su e-CF de reemplazo."""
	return frappe.get_list(
		FACTURA,
		filters={
			"company": company,
			"docstatus": 1,
			"rd_contingencia_ecf": 1,
			"rd_encf_reemplazo": ("is", "not set"),
		},
		fields=["name", "rd_ncf", "rd_tipo_comprobante", "posting_date", "grand_total", "rd_plazo_reemplazo"],
		order_by="posting_date asc",
		limit=limite,
	)


@frappe.whitelist(methods=["POST"])
def emitir_reemplazo(name: str) -> str:
	"""Firma (y envía a la DGII, si el emisor está habilitado) el e-CF que reemplaza el comprobante de
	la serie B de una factura emitida en contingencia. Devuelve el *Envio ECF*."""
	doc = frappe.get_doc(FACTURA, name)
	doc.check_permission("submit")
	if doc.docstatus != 1 or not cint(doc.get("rd_contingencia_ecf")):
		frappe.throw(_("La factura no se emitió en contingencia con un comprobante de la serie B."))
	if doc.rd_encf_reemplazo:
		frappe.throw(_("La factura ya tiene su e-CF de reemplazo: {0}.").format(doc.rd_encf_reemplazo))
	tipo = EQUIVALENTES.get(doc.rd_tipo_comprobante)
	if not tipo:
		frappe.throw(_("El comprobante {0} no tiene e-CF de reemplazo.").format(doc.rd_tipo_comprobante))

	isc.validar_ecf(doc)
	emisor = emision.emisor_de(doc.company)
	ncf_b = doc.rd_ncf
	siguiente = ncf.tomar_siguiente_ncf(doc.company, tipo)
	# El e-CF se arma con el tipo y el e-NCF nuevos; la factura conserva su NCF de la serie B
	doc.rd_tipo_comprobante, doc.rd_ncf, doc.rd_ncf_vencimiento = tipo, siguiente.ncf, siguiente.vencimiento
	fecha_firma = now_datetime()
	contenido = datos.datos_ecf(doc, fecha_firma)
	contenido["InformacionReferencia"] = {
		"NCFModificado": ncf_b,
		"FechaNCFModificado": datos.fecha(doc.posting_date),
		"CodigoModificacion": REEMPLAZO_CONTINGENCIA,
	}
	envio = emision.registrar(
		emisor,
		int(tipo[1:]),
		contenido,
		{
			"tipo_documento": FACTURA,
			"documento": name,
			"fecha_firma": fecha_firma,
			"es_reemplazo": 1,
			"ncf_reemplazado": ncf_b,
		},
		es_rfce=tipo == "E32" and flt(doc.grand_total) < flt(emisor.monto_rfce),
	)
	frappe.db.set_value(FACTURA, name, "rd_encf_reemplazo", envio.encf, update_modified=False)
	if emisor.habilitado:
		emision.enviar_a_dgii(envio, emisor)
	return envio.name
