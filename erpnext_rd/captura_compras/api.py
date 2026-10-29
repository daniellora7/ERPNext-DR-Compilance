"""API de la captura de compras: la pantalla del celular (/rd-compliance/escanear) y los botones del
escritorio. Los métodos que escriben solo aceptan POST."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_rd.captura_compras import convertir, qr
from erpnext_rd.dgii_fiscal.catalogos import TIPOS_BIENES_SERVICIOS
from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.ecf.emision import leer_xml, rnc_empresa

CAPTURA = convertir.CAPTURA
ROL = "Captura Compras RD"
CAMPOS_LISTA = [
	"name",
	"estado",
	"estado_dgii",
	"encf",
	"razon_social_emisor",
	"rnc_emisor",
	"monto_total",
	"total_itbis",
	"fecha_emision",
	"creation",
	"avisos",
]


@frappe.whitelist()
def contexto() -> dict:
	"""Empresas RD del usuario y los tipos de gasto del 606."""
	frappe.has_permission(CAPTURA, "create", throw=True)
	empresas = [
		e
		for e in frappe.get_list("Company", fields=["name", "company_name", "tax_id"], order_by="name")
		if es_empresa_rd(e.name)
	]
	predeterminada = frappe.defaults.get_user_default("Company")
	nombres = [e.name for e in empresas]
	return {
		"empresas": empresas,
		"empresa": predeterminada if predeterminada in nombres else (nombres[0] if nombres else None),
		"tipos_606": TIPOS_BIENES_SERVICIOS,
	}


@frappe.whitelist(methods=["POST"])
def crear(
	company: str,
	url_timbre: str | None = None,
	file_url: str | None = None,
	total_itbis: float | None = None,
	rd_tipo_bienes_servicios: str | None = None,
	id_cliente: str | None = None,
) -> dict:
	"""Crea la captura desde el QR, la foto o el PDF. `id_cliente` (lo genera el celular) evita
	duplicarla si un envío sin conexión se reintenta."""
	if id_cliente and (existente := frappe.db.get_value(CAPTURA, {"id_cliente": id_cliente})):
		return _resumen(frappe.get_doc(CAPTURA, existente))
	if not (url_timbre or file_url):
		frappe.throw(_("Escanee el QR o adjunte la foto o el PDF de la factura."))

	doc = frappe.new_doc(CAPTURA)
	doc.update(
		{
			"company": company,
			"url_timbre": url_timbre,
			"id_cliente": id_cliente,
			"rd_tipo_bienes_servicios": rd_tipo_bienes_servicios,
		}
	)
	archivo = _archivo(file_url) if file_url else None
	if archivo:
		doc.archivo = archivo.file_url
		doc.origen = "PDF" if archivo.file_url.lower().endswith(".pdf") else "Foto"
		if doc.origen == "PDF":
			_datos_del_pdf(doc, leer_xml(archivo.file_url))
	if total_itbis is not None and str(total_itbis) != "":
		doc.update({"total_itbis": flt(total_itbis), "fuente_montos": "Manual"})
	doc.insert()
	# Frappe adjunta el archivo del campo «archivo» al guardar la captura
	return _resumen(doc)


def _archivo(file_url: str):
	"""El archivo que el usuario acaba de subir (suyo y sin adjuntar a otro documento)."""
	nombre = frappe.db.get_value(
		"File",
		{"file_url": file_url, "owner": frappe.session.user, "attached_to_name": ("is", "not set")},
	)
	if not nombre:
		frappe.throw(_("No se encontró el archivo subido."))
	return frappe.get_doc("File", nombre)


def _datos_del_pdf(doc, contenido: bytes):
	"""Datos y montos del texto del PDF. Si también vino el QR, sus datos mandan y el total del PDF
	tiene que ser igual."""
	datos = qr.leer_pdf(contenido, rnc_empresa(doc.company))
	if not datos:
		doc.observaciones = _("El PDF no tiene texto (escaneado): escriba el ITBIS.")
		return
	if not doc.url_timbre:
		doc.update({k: v for k, v in datos.items() if k not in ("total_itbis", "monto_exento")})
	total_qr = qr.leer_url(doc.url_timbre)["monto_total"] if doc.url_timbre else datos.get("monto_total")
	if "total_itbis" in datos and abs(flt(datos.get("monto_total")) - flt(total_qr)) <= 0.01:
		doc.update(
			{
				"total_itbis": datos["total_itbis"],
				"monto_exento": datos.get("monto_exento"),
				"fuente_montos": "Texto del PDF",
			}
		)


@frappe.whitelist(methods=["POST"])
def completar(name: str, total_itbis: float, rd_tipo_bienes_servicios: str | None = None) -> dict:
	"""El usuario escribe el ITBIS (y el tipo de gasto) que no se pudo leer."""
	doc = frappe.get_doc(CAPTURA, name)
	doc.check_permission("write")
	doc.update({"total_itbis": flt(total_itbis), "fuente_montos": "Manual"})
	if rd_tipo_bienes_servicios:
		doc.rd_tipo_bienes_servicios = rd_tipo_bienes_servicios
	doc.save()
	return _resumen(doc)


@frappe.whitelist()
def mis_capturas(limit: int = 20) -> list:
	return frappe.get_list(
		CAPTURA,
		filters={"owner": frappe.session.user},
		fields=CAMPOS_LISTA,
		order_by="creation desc",
		limit_page_length=min(cint(limit) or 20, 100),
	)


def _resumen(doc) -> dict:
	return {campo: doc.get(campo) for campo in CAMPOS_LISTA}


# ---------------------------------------------------------------- escritorio


@frappe.whitelist(methods=["POST"])
def verificar(name: str) -> str:
	"""Botón «Verificar en la DGII»."""
	doc = frappe.get_doc(CAPTURA, name)
	doc.check_permission("write")
	qr.verificar(doc)
	doc.save()
	return doc.estado_dgii


def verificar_en_segundo_plano(name: str):
	doc = frappe.get_doc(CAPTURA, name)
	qr.verificar(doc)
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def crear_factura(name: str) -> str:
	doc = frappe.get_doc(CAPTURA, name)
	doc.check_permission("write")
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	return convertir.desde_captura(doc)


@frappe.whitelist(methods=["POST"])
def descartar(name: str, motivo: str | None = None) -> str:
	doc = frappe.get_doc(CAPTURA, name)
	doc.check_permission("write")
	if doc.factura_compra:
		frappe.throw(_("La captura ya tiene la factura de compra {0}.").format(doc.factura_compra))
	doc.estado = "Descartada"
	if motivo:
		doc.observaciones = motivo
	doc.save()
	return doc.estado
