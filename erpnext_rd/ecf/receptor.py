"""Servicios públicos del receptor electrónico, en las rutas que fija la DGII bajo la URL del sitio.

La URL del sitio (p. ej. https://erp.empresa.com.do) se registra en el portal de la DGII como receptor;
emisores y DGII llaman:

- GET  /fe/autenticacion/api/semilla               → semilla XML para firmar
- POST /fe/autenticacion/api/validacioncertificado → semilla firmada; responde {token, expira, expedido}
- POST /fe/recepcion/api/ecf                       → e-CF (bearer); responde el acuse de recibo (ARECF)
- POST /fe/aprobacioncomercial/api/ecf             → aprobación comercial (bearer) de un e-CF emitido

Frappe pasa a los `page_renderer` de las apps las rutas que no son /api ni archivos; este las atiende
como invitado (sin sesión ni CSRF) y Frappe confirma la transacción al terminar el POST. Varias empresas
del sitio comparten las rutas: se distinguen por el RNC del comprador o del emisor del documento.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime
from frappe.website.page_renderers.base_renderer import BaseRenderer
from lxml import etree
from werkzeug.wrappers import Response

from erpnext_rd.ecf import firma, recepcion

SEMILLA_SEGUNDOS = 300
TOKEN_SEGUNDOS = 3600
TAMANO_MAXIMO = 5 * 1024 * 1024  # un e-CF de 1 000 líneas firmado ronda 1 MB


def _clave(tipo: str, valor: str) -> str:
	return f"erpnext_rd:receptor:{tipo}:{valor}"


def _iso(fecha) -> str:
	return fecha.strftime("%Y-%m-%dT%H:%M:%S")


def _json(datos: dict, estado: int = 200) -> Response:
	return Response(json.dumps(datos, ensure_ascii=False), status=estado, mimetype="application/json")


def _xml(contenido: bytes) -> Response:
	return Response(contenido, status=200, mimetype="application/xml")


def _archivo() -> bytes:
	"""El XML del campo multipart `xml` (o el cuerpo de la petición)."""
	if (frappe.request.content_length or 0) > TAMANO_MAXIMO:
		raise recepcion.ErrorRecepcion(_("El archivo es demasiado grande"))
	archivo = frappe.request.files.get("xml") or next(iter(frappe.request.files.values()), None)
	contenido = archivo.read(TAMANO_MAXIMO + 1) if archivo else frappe.request.get_data()
	if not contenido or len(contenido) > TAMANO_MAXIMO:
		raise recepcion.ErrorRecepcion(_("Falta el archivo XML"))
	return contenido


def semilla() -> Response:
	valor = secrets.token_urlsafe(32)
	frappe.cache.set_value(_clave("semilla", valor), 1, expires_in_sec=SEMILLA_SEGUNDOS)
	xml = (
		'<?xml version="1.0" encoding="utf-8"?>'
		'<SemillaModel xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
		f"<valor>{valor}</valor><fecha>{_iso(now_datetime())}</fecha></SemillaModel>"
	)
	return _xml(xml.encode())


def validar_certificado() -> Response:
	xml = _archivo()
	try:
		valor = (firma.leer(xml).findtext("valor") or "").strip()
	except etree.XMLSyntaxError:
		valor = ""
	if not valor or not frappe.cache.get_value(_clave("semilla", valor)) or not firma.verificar(xml):
		return _json({"mensaje": _("Semilla vencida, desconocida o mal firmada")}, 401)
	frappe.cache.delete_value(_clave("semilla", valor))

	token = secrets.token_urlsafe(32)
	frappe.cache.set_value(_clave("token", token), 1, expires_in_sec=TOKEN_SEGUNDOS)
	ahora = now_datetime()
	return _json(
		{
			"token": token,
			"expira": _iso(add_to_date(ahora, seconds=TOKEN_SEGUNDOS)),
			"expedido": _iso(ahora),
		}
	)


def _token_valido() -> bool:
	encabezado = frappe.get_request_header("Authorization") or ""
	tipo, _espacio, token = encabezado.partition(" ")
	return (
		tipo.lower() == "bearer"
		and bool(token)
		and bool(frappe.cache.get_value(_clave("token", token.strip())))
	)


def autenticar():
	"""auth_hooks: Frappe toma cualquier «Authorization: bearer …» como un token OAuth suyo y, si no lo
	conoce, corta la petición con 401 antes de llegar aquí. En las rutas del receptor, un token emitido
	por validar_certificado se acepta: Frappe exige un usuario en ese caso y el renderizador vuelve a
	invitado antes de atender (ver ReceptorECF.render), así nada corre con ese usuario."""
	if frappe.request and frappe.request.path.strip("/").lower() in RUTAS and _token_valido():
		frappe.local.flags.receptor_ecf = True
		frappe.set_user("Administrator")


def _autenticado() -> bool:
	return bool(frappe.local.flags.receptor_ecf)


def recibir_ecf() -> Response:
	if not _autenticado():
		return _json({"mensaje": _("Token no válido; autentíquese primero")}, 401)
	return _xml(recepcion.recibir_ecf(_archivo()))


def recibir_aprobacion() -> Response:
	if not _autenticado():
		return _json({"mensaje": _("Token no válido; autentíquese primero")}, 401)
	recepcion.recibir_aprobacion(_archivo())
	return _json({"mensaje": _("Aprobación comercial recibida")})


RUTAS = {
	"fe/autenticacion/api/semilla": ("GET", semilla),
	"fe/autenticacion/api/validacioncertificado": ("POST", validar_certificado),
	"fe/recepcion/api/ecf": ("POST", recibir_ecf),
	"fe/aprobacioncomercial/api/ecf": ("POST", recibir_aprobacion),
}


class ReceptorECF(BaseRenderer):
	"""page_renderer de hooks.py: atiende solo las rutas de RUTAS."""

	def can_render(self):
		return self.path.lower() in RUTAS

	def render(self):
		if frappe.local.flags.receptor_ecf:
			frappe.set_user("Guest")
		metodo, servicio = RUTAS[self.path.lower()]
		if frappe.request.method != metodo:
			return _json({"mensaje": _("Método no permitido")}, 405)
		try:
			return servicio()
		except recepcion.ErrorRecepcion as error:
			return _json({"mensaje": str(error)}, 400)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(_("Servicio del receptor e-CF: {0}").format(self.path))
			frappe.db.commit()  # nosemgrep: el registro del error queda aunque la respuesta sea 500
			return _json({"mensaje": _("Error interno del receptor")}, 500)
