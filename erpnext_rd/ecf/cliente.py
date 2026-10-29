"""Servicios web de facturación electrónica de la DGII («Descripción técnica servicios DGII»).

Ambientes: TesteCF (pre-certificación), CerteCF (certificación) y eCF (producción); el de la
Configuración DGII. Flujo:

1. Autenticación: GET semilla → se firma con el certificado del emisor → POST validarsemilla devuelve
   un token *bearer* (se guarda en caché hasta su vencimiento).
2. Recepción del e-CF: POST del XML firmado (multipart, campo `xml`, nombre RNC + e-NCF) → trackId.
   Las facturas de consumo (E32) menores al monto de la configuración van como resumen (RFCE) al
   servicio de recepción FC, que responde directamente el estado.
3. Consulta del resultado por trackId (Aceptado, Aceptado condicional, Rechazado, En proceso).
4. Anulación de rangos de e-NCF no usados (ANECF), copia de la aprobación comercial (ACECF) y consulta
   del directorio de receptores electrónicos (URLs de otro contribuyente).

`ClienteReceptor` habla directamente con otro contribuyente (entrega del e-CF al comprador y de la
aprobación comercial al emisor). Un servicio que no responde (5xx, 429, sin conexión) es contingencia:
el envío se reintenta (ver `emision.reintentar_contingencia`).
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, now_datetime

from erpnext_rd.ecf import firma

AMBIENTES = {"TesteCF": "testecf", "CerteCF": "certecf", "eCF": "ecf"}
ECF = "https://ecf.dgii.gov.do/{ambiente}"
FC = "https://fc.dgii.gov.do/{ambiente}"
TIEMPO_ESPERA = 60


class ErrorDGII(frappe.ValidationError):
	def __init__(self, mensaje="", codigo: int | None = None):
		super().__init__(mensaje)
		self.codigo = codigo

	@property
	def sin_servicio(self) -> bool:
		"""El servicio no respondió (caído, saturado): se reintenta más tarde (contingencia)."""
		return self.codigo is None or self.codigo >= 500 or self.codigo == 429


class ClienteDGII:
	def __init__(self, rnc: str, llave, certificado, ambiente: str | None = None, sesion=None):
		self.rnc = rnc
		self.llave = llave
		self.certificado = certificado
		self.ambiente = (
			ambiente or frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF"
		)
		self.ruta = AMBIENTES[self.ambiente]
		self.sesion = sesion or requests.Session()

	# ------------------------------------------------------------- utilidades

	def _url(self, base: str, recurso: str) -> str:
		# El servicio FC de certificación usa la ruta con mayúscula inicial (Certecf), como la publica la DGII
		ambiente = "Certecf" if base == FC and self.ruta == "certecf" else self.ruta
		return base.format(ambiente=ambiente) + recurso

	def _respuesta(self, r: requests.Response) -> dict:
		try:
			datos = r.json()
		except ValueError:
			datos = {"mensaje": r.text[:500]}
		if r.status_code >= 400:
			raise ErrorDGII(
				_("La DGII respondió {0}: {1}").format(
					r.status_code, json.dumps(datos, ensure_ascii=False)[:500]
				),
				r.status_code,
			)
		return datos

	def _clave_cache(self) -> str:
		return f"erpnext_rd:ecf_token:{self.ambiente}:{self.rnc}"

	# ---------------------------------------------------------- autenticación

	def semilla(self) -> bytes:
		r = self.sesion.get(self._url(ECF, "/autenticacion/api/autenticacion/semilla"), timeout=TIEMPO_ESPERA)
		if r.status_code >= 400:
			raise ErrorDGII(
				_("No se pudo obtener la semilla de la DGII ({0})").format(r.status_code), r.status_code
			)
		return r.content

	def token(self) -> str:
		"""Token vigente (de la caché o uno nuevo con la semilla firmada)."""
		guardado = frappe.cache.get_value(self._clave_cache())
		if guardado and get_datetime(guardado["expira"]) > now_datetime():
			return guardado["token"]
		semilla_firmada = firma.firmar(self.semilla(), self.llave, self.certificado)
		r = self.sesion.post(
			self._url(ECF, "/autenticacion/api/autenticacion/validarsemilla"),
			files={"xml": ("semilla.xml", semilla_firmada, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		datos = self._respuesta(r)
		if not datos.get("token"):
			raise ErrorDGII(_("La DGII no devolvió el token: {0}").format(datos))
		expira = (
			get_datetime(str(datos.get("expira", "")).replace("Z", "").replace("T", " ")[:19])
			or now_datetime()
		)
		frappe.cache.set_value(
			self._clave_cache(),
			{"token": datos["token"], "expira": str(expira)},
			expires_in_sec=max(int((expira - now_datetime()).total_seconds()) - 60, 60),
		)
		return datos["token"]

	def _autorizacion(self) -> dict:
		return {"Authorization": f"bearer {self.token()}", "accept": "application/json"}

	# ----------------------------------------------------------------- envíos

	def enviar_ecf(self, xml_firmado: bytes, encf: str) -> dict:
		"""Recepción de e-CF: devuelve {trackId, error, mensaje}."""
		r = self.sesion.post(
			self._url(ECF, "/recepcion/api/facturaselectronicas"),
			headers=self._autorizacion(),
			files={"xml": (f"{self.rnc}{encf}.xml", xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)

	def enviar_rfce(self, xml_firmado: bytes, encf: str) -> dict:
		"""Resumen de factura de consumo: devuelve {codigo, estado, mensajes, encf, secuenciaUtilizada}."""
		r = self.sesion.post(
			self._url(FC, "/recepcionfc/api/recepcion/ecf"),
			headers=self._autorizacion(),
			files={"xml": (f"{self.rnc}{encf}.xml", xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)

	def anular_rangos(self, xml_firmado: bytes, nombre: str) -> dict:
		"""Anulación de rangos de e-NCF no utilizados (ANECF): devuelve {rnc, codigo, nombre, mensajes}."""
		r = self.sesion.post(
			self._url(ECF, "/anulacionrangos/api/operaciones/anularrango"),
			headers=self._autorizacion(),
			files={"xml": (nombre, xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)

	def enviar_aprobacion(self, xml_firmado: bytes, nombre: str) -> dict:
		"""Aprobación o rechazo comercial (ACECF) de un e-CF recibido: copia para la DGII."""
		r = self.sesion.post(
			self._url(ECF, "/aprobacioncomercial/api/aprobacioncomercial"),
			headers=self._autorizacion(),
			files={"xml": (nombre, xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)

	# --------------------------------------------------------------- consultas

	def directorio(self, rnc: str) -> dict | None:
		"""URLs del contribuyente si es receptor electrónico ({urlRecepcion, urlAceptacion, urlOpcional})."""
		r = self.sesion.get(
			self._url(ECF, "/consultadirectorio/api/consultas/obtenerdirectorioporrnc"),
			headers=self._autorizacion(),
			params={"RNC": rnc},
			timeout=TIEMPO_ESPERA,
		)
		if r.status_code == 404:
			return None
		datos = self._respuesta(r)
		if isinstance(datos, list):
			datos = datos[0] if datos else None
		return datos if datos and datos.get("urlRecepcion") else None

	def consultar_resultado(self, track_id: str) -> dict:
		r = self.sesion.get(
			self._url(ECF, "/consultaresultado/api/consultas/estado"),
			headers=self._autorizacion(),
			params={"trackid": track_id},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)

	def consultar_estado(
		self, encf: str, rnc_comprador: str | None, codigo_seguridad: str, rnc_emisor: str | None = None
	) -> dict:
		"""Estado de un e-CF. Por defecto uno emitido por la empresa; con `rnc_emisor`, el de un
		proveedor (la empresa como compradora)."""
		r = self.sesion.get(
			self._url(ECF, "/consultaestado/api/consultas/estado"),
			headers=self._autorizacion(),
			params={
				"rncemisor": rnc_emisor or self.rnc,
				"ncfelectronico": encf,
				"rnccomprador": rnc_comprador or "",
				"codigoseguridad": codigo_seguridad,
			},
			timeout=TIEMPO_ESPERA,
		)
		return self._respuesta(r)


class ClienteReceptor:
	"""Intercambio directo con otro contribuyente electrónico, en las URLs que publica en el directorio
	de la DGII: entrega del e-CF al comprador (responde el acuse de recibo, ARECF) y de la aprobación
	comercial (ACECF) al emisor. Las rutas son las del estándar de la DGII bajo la URL registrada:
	/fe/autenticacion/api/semilla, /fe/autenticacion/api/validacioncertificado, /fe/recepcion/api/ecf y
	/fe/aprobacioncomercial/api/ecf. Si el receptor no tiene autenticación se envía sin token."""

	def __init__(self, urls: dict, llave, certificado, sesion=None):
		self.urls = urls
		self.llave = llave
		self.certificado = certificado
		self.sesion = sesion or requests.Session()
		self._token = None

	@staticmethod
	def _base(url: str | None) -> str:
		return (url or "").split("/fe/")[0].rstrip("/")

	def _url(self, clave: str, ruta: str) -> str:
		base = self._base(self.urls.get(clave) or self.urls.get("urlRecepcion"))
		if not base:
			raise ErrorDGII(_("El receptor no tiene URL de servicio"), 404)
		return base + ruta

	def _encabezados(self) -> dict:
		if self._token is None:
			try:
				semilla = self.sesion.get(
					self._url("urlOpcional", "/fe/autenticacion/api/semilla"), timeout=TIEMPO_ESPERA
				)
				if semilla.status_code >= 400:
					raise ErrorDGII("", semilla.status_code)
				r = self.sesion.post(
					self._url("urlOpcional", "/fe/autenticacion/api/validacioncertificado"),
					files={
						"xml": ("semilla.xml", firma.firmar(semilla.content, self.llave, self.certificado))
					},
					timeout=TIEMPO_ESPERA,
				)
				self._token = (r.json() or {}).get("token") or "" if r.status_code < 400 else ""
			except (ErrorDGII, OSError, ValueError):
				self._token = ""
		return {"Authorization": f"bearer {self._token}"} if self._token else {}

	def enviar_ecf(self, xml_firmado: bytes, nombre: str) -> bytes:
		"""Entrega el e-CF; devuelve el acuse de recibo (ARECF) firmado por el comprador."""
		r = self.sesion.post(
			self._url("urlRecepcion", "/fe/recepcion/api/ecf"),
			headers=self._encabezados(),
			files={"xml": (nombre, xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		if r.status_code >= 400:
			raise ErrorDGII(
				_("El comprador respondió {0}: {1}").format(r.status_code, r.text[:300]), r.status_code
			)
		return r.content

	def enviar_aprobacion(self, xml_firmado: bytes, nombre: str):
		r = self.sesion.post(
			self._url("urlAceptacion", "/fe/aprobacioncomercial/api/ecf"),
			headers=self._encabezados(),
			files={"xml": (nombre, xml_firmado, "text/xml")},
			timeout=TIEMPO_ESPERA,
		)
		if r.status_code >= 400:
			raise ErrorDGII(
				_("El emisor respondió {0}: {1}").format(r.status_code, r.text[:300]), r.status_code
			)
