"""Captura de compras, etapa 2: e-CF entregado impreso o en PDF (y la factura en papel sin QR).

- `leer_url`: datos del QR (URL de consulta del timbre de la DGII). Solo se aceptan los dominios de la
  DGII: el QR de una factura falsa puede apuntar a cualquier lado.
- `leer_pdf` / `leer_texto`: los mismos datos y los montos desde el texto de un PDF generado por el
  sistema del proveedor (la representación impresa del e-CF trae RNC, e-NCF, código de seguridad,
  fecha de firma, ITBIS y total). Un PDF escaneado no tiene texto: queda para revisión.
- `verificar`: consulta el estado del e-CF en la DGII con el certificado de la empresa.
- `verificar_ncf`: sin código de seguridad, la consulta pública de NCF (vigencia y si es del emisor).
"""

import io
import re
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime

from erpnext_rd.dgii_fiscal import consulta_ncf
from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion
from erpnext_rd.ecf.cliente import ClienteDGII, ErrorDGII
from erpnext_rd.ecf.emision import EMISOR, rnc_empresa

HOSTS = {"ecf.dgii.gov.do": "ConsultaTimbre", "fc.dgii.gov.do": "ConsultaTimbreFC"}
ESTADOS_DGII = (
	("condicional", "Aceptado condicional"),
	("aceptado", "Aceptado"),
	("rechazado", "Rechazado"),
	("no encontrado", "No encontrado"),
)
_ENCF = re.compile(r"\bE\d{12}\b")
_MONTO = r"(?:RD\$|\$)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2})"


def _fecha(texto: str | None):
	"""dd-mm-aaaa (o con /) -> fecha."""
	if not texto:
		return None
	try:
		dia, mes, anio = re.split(r"[-/]", texto.strip())
		return getdate(f"{anio}-{mes}-{dia}")
	except ValueError:
		return None


def _fecha_hora(texto: str | None):
	if not texto:
		return None
	fecha, _sep, hora = texto.strip().partition(" ")
	dia = _fecha(fecha)
	try:
		return get_datetime(f"{dia} {hora}") if dia and hora else None
	except Exception:
		return None


def leer_url(url: str) -> dict:
	"""Datos del QR de un e-CF. Lanza ValidationError si no es una URL de timbre de la DGII."""
	partes = urlsplit((url or "").strip())
	pagina = HOSTS.get((partes.hostname or "").lower())
	if partes.scheme != "https" or not pagina or not partes.path.rstrip("/").endswith("/" + pagina):
		frappe.throw(_("El QR no es de un comprobante electrónico de la DGII."), title=_("QR no válido"))
	p = {k.lower(): v[0].strip() for k, v in parse_qs(partes.query).items() if v}
	datos = {
		"url_timbre": url.strip(),
		"rnc_emisor": limpiar_identificacion(p.get("rncemisor")),
		"rnc_comprador": limpiar_identificacion(p.get("rnccomprador")) or None,
		"encf": (p.get("encf") or "").upper(),
		"fecha_emision": _fecha(p.get("fechaemision")),
		"monto_total": flt(p.get("montototal")),
		"fecha_firma": _fecha_hora(p.get("fechafirma")),
		"codigo_seguridad": p.get("codigoseguridad"),
	}
	if not (datos["rnc_emisor"] and _ENCF.fullmatch(datos["encf"]) and datos["codigo_seguridad"]):
		frappe.throw(_("Al QR le falta el RNC del emisor, el e-NCF o el código de seguridad."))
	return datos


def leer_pdf(contenido: bytes, rnc_comprador: str | None = None) -> dict:
	from pdfminer.high_level import extract_text

	try:
		texto = extract_text(io.BytesIO(contenido), maxpages=3)
	except Exception:
		return {}
	return leer_texto(texto, rnc_comprador)


def leer_texto(texto: str, rnc_comprador: str | None = None) -> dict:
	"""Datos y montos del e-CF desde el texto de su representación impresa."""
	texto = texto or ""
	datos = {}
	if m := _ENCF.search(texto):
		datos["encf"] = m.group(0)

	rncs = []
	for numero in re.findall(r"(?<![\d-])(\d{3}-?\d{5}-?\d|\d{3}-?\d{7}-?\d)(?![\d-])", texto):
		numero = limpiar_identificacion(numero)
		if numero not in rncs:
			rncs.append(numero)
	if rnc_comprador in rncs:
		datos["rnc_comprador"] = rnc_comprador
	if emisores := [r for r in rncs if r != rnc_comprador]:
		datos["rnc_emisor"] = emisores[0]

	patrones = {
		"codigo_seguridad": r"C[oó]digo\s+de\s+seguridad\s*:?\s*([A-Za-z0-9]{6})\b",
		"fecha_firma": r"Fecha\s+(?:y\s+hora\s+)?de\s+(?:la\s+)?firma\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4}\s+\d{2}:\d{2}(?::\d{2})?)",
		"fecha_emision": r"Fecha\s+(?:de\s+)?emisi[oó]n\s*:?\s*(\d{2}[-/]\d{2}[-/]\d{4})",
	}
	for campo, patron in patrones.items():
		if m := re.search(patron, texto, re.I):
			datos[campo] = m.group(1)
	datos["fecha_emision"] = _fecha(datos.get("fecha_emision"))
	datos["fecha_firma"] = _fecha_hora(datos.get("fecha_firma"))

	def montos(patron):
		return [flt(m.replace(",", "")) for m in re.findall(patron + r"[^\d\n]{0,30}?" + _MONTO, texto, re.I)]

	totales = montos(r"(?<![A-Za-z])Total(?!\s*(?:de\s+)?(?:ITBIS|exento|gravado|descuento))")
	itbis = montos(r"Total\s+(?:de\s+)?ITBIS") or montos(r"(?<![A-Za-z])ITBIS(?:\s*\d{1,2}\s*%)?")
	exento = montos(r"(?:Monto|Total)\s+exento")
	if totales:
		datos["monto_total"] = max(totales)
	if itbis:
		datos["total_itbis"] = max(itbis)
	if exento:
		datos["monto_exento"] = max(exento)
	return {k: v for k, v in datos.items() if v not in (None, "")}


def verificar(doc) -> str:
	"""Consulta el estado del e-CF en la DGII. Sin emisor e-CF de la empresa no hay con qué
	autenticarse: queda «Sin verificar» y el usuario puede abrir la URL del timbre. Sin código de
	seguridad (NCF escrito a mano), se usa la consulta pública de NCF."""
	if not doc.codigo_seguridad:
		return verificar_ncf(doc)
	emisor = frappe.db.get_value(EMISOR, doc.company, "certificado")
	if not emisor:
		doc.mensaje_dgii = _("La empresa no tiene emisor e-CF: verifique el e-CF con el enlace del QR.")
		return doc.estado_dgii
	llave, certificado = frappe.get_doc(EMISOR, doc.company).cargar()
	cliente = ClienteDGII(rnc_empresa(doc.company), llave, certificado)
	try:
		respuesta = cliente.consultar_estado(
			doc.encf, doc.rnc_comprador, doc.codigo_seguridad, rnc_emisor=doc.rnc_emisor
		)
	except (ErrorDGII, OSError) as error:
		doc.update(
			{"estado_dgii": "Error", "mensaje_dgii": str(error)[:500], "verificado_en": now_datetime()}
		)
		return doc.estado_dgii
	estado = str(respuesta.get("estado") or "").lower()
	doc.update(
		{
			"estado_dgii": next((e for clave, e in ESTADOS_DGII if clave in estado), "No encontrado"),
			"mensaje_dgii": str(respuesta.get("mensaje") or respuesta.get("estado") or "")[:500],
			"verificado_en": now_datetime(),
		}
	)
	# Si la respuesta trae el ITBIS y nadie lo escribió, se toma de la DGII
	if respuesta.get("totalITBIS") is not None and not doc.fuente_montos:
		doc.update({"total_itbis": flt(respuesta["totalITBIS"]), "fuente_montos": "DGII"})
	return doc.estado_dgii


def verificar_ncf(doc) -> str:
	"""NCF escrito a mano (factura en papel o e-CF sin QR): consulta pública de NCF de la DGII. Un
	NCF vencido sirve si la factura es de antes del vencimiento."""
	if not (doc.encf and doc.rnc_emisor):
		return doc.estado_dgii
	comprador = rnc_empresa(doc.company) if doc.encf.startswith("E") else None
	resultado = consulta_ncf.consultar(doc.rnc_emisor, doc.encf, comprador)
	doc.update(
		{
			"estado_dgii": consulta_ncf.estado_para_la_fecha(resultado, doc.fecha_emision),
			"mensaje_dgii": resultado.mensaje,
			"verificado_en": now_datetime(),
		}
	)
	if resultado.razon_social and not doc.razon_social_emisor:
		doc.razon_social_emisor = resultado.razon_social
	return doc.estado_dgii
