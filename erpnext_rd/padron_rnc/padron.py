"""Padrón de contribuyentes de la DGII: descarga, importación y consulta."""

import io
import time
import zipfile
from datetime import timedelta
from email.utils import format_datetime, parsedate_to_datetime

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion

# Archivo público de la DGII (texto separado por "|", codificación latin-1):
# RNC|RAZÓN SOCIAL|NOMBRE COMERCIAL|ACTIVIDAD|...|...|...|...|FECHA INICIO|ESTADO|RÉGIMEN
URL_PADRON = "https://www.dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip"
LOTE = 5000
# La DGII sirve el archivo desde varios servidores cuyas copias difieren por segundos en su fecha
# (Last-Modified): dos fechas a menos de una hora se consideran la misma versión.
MARGEN_VERSION = timedelta(hours=1)


def _fecha_http(valor: str | None):
	try:
		return parsedate_to_datetime(valor) if valor else None
	except (TypeError, ValueError):
		return None


def parsear_linea(linea: str) -> tuple | None:
	partes = [p.strip() for p in linea.rstrip("\r\n").split("|")]
	if len(partes) < 11:
		return None
	rnc = limpiar_identificacion(partes[0])
	if len(rnc) not in (9, 11):
		return None
	return (
		rnc,
		partes[1][:255],
		partes[2][:255],
		partes[3][:255],
		partes[8][:10],
		partes[9][:30],
		partes[10][:30],
	)


def descargar_padron(version: str | None = None, intentos: int = 4) -> tuple[bytes | None, str | None]:
	"""Descarga el ZIP si la DGII publicó uno más reciente que `version` (su Last-Modified).

	Devuelve (contenido, versión). Sin cambios el servidor responde 304 sin enviar el archivo y el
	contenido es None. El servidor de la DGII a veces corta la conexión: se reintenta."""
	encabezados = {"User-Agent": "Mozilla/5.0 ERPNext-RD"}
	limite = _fecha_http(version) and _fecha_http(version) + MARGEN_VERSION
	if limite:
		encabezados["If-Modified-Since"] = format_datetime(limite, usegmt=True)

	for intento in range(1, intentos + 1):
		try:
			respuesta = requests.get(URL_PADRON, timeout=300, headers=encabezados)
			respuesta.raise_for_status()
			nueva = respuesta.headers.get("Last-Modified")
			# 304, o un servidor que ignora If-Modified-Since pero envía la misma versión
			fecha = _fecha_http(nueva)
			if respuesta.status_code == 304 or (limite and fecha and fecha <= limite):
				return None, version
			zipfile.ZipFile(io.BytesIO(respuesta.content)).testzip()
			return respuesta.content, nueva
		except (requests.RequestException, zipfile.BadZipFile):
			if intento == intentos:
				raise
			time.sleep(10 * intento)


def importar_padron(contenido_zip: bytes) -> int:
	"""Inserta o actualiza todos los contribuyentes. Devuelve la cantidad procesada."""
	ahora = now_datetime()
	usuario = frappe.session.user or "Administrator"
	total = 0
	lote = []

	with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
		nombre = next(n for n in zf.namelist() if n.upper().endswith((".TXT", ".CSV")))
		with zf.open(nombre) as f:
			for crudo in io.TextIOWrapper(f, encoding="latin-1"):
				fila = parsear_linea(crudo)
				if not fila:
					continue
				lote.append(fila)
				if len(lote) >= LOTE:
					total += _guardar_lote(lote, ahora, usuario)
					lote = []
	if lote:
		total += _guardar_lote(lote, ahora, usuario)
	return total


def _guardar_lote(lote: list[tuple], ahora, usuario) -> int:
	valores = [(f[0], *f, ahora, ahora, usuario, usuario) for f in lote]
	frappe.db.sql(
		"""
		INSERT INTO `tabContribuyente DGII`
			(name, rnc, razon_social, nombre_comercial, actividad_economica, fecha_inicio, estado,
			 regimen_pago, creation, modified, owner, modified_by)
		VALUES {}
		ON DUPLICATE KEY UPDATE
			razon_social = VALUES(razon_social),
			nombre_comercial = VALUES(nombre_comercial),
			actividad_economica = VALUES(actividad_economica),
			fecha_inicio = VALUES(fecha_inicio),
			estado = VALUES(estado),
			regimen_pago = VALUES(regimen_pago),
			modified = VALUES(modified)
		""".format(", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(valores))),
		[v for fila in valores for v in fila],
	)
	frappe.db.commit()
	return len(lote)


def sincronizar_padron(forzar: bool = False) -> int | None:
	"""Descarga e importa el padrón completo (~800 mil registros) si la DGII publicó una versión
	nueva. Devuelve los registros procesados, o None si no hubo cambios.

	`forzar` (botón de Configuración DGII) descarga aunque la versión sea la misma; con el padrón
	vacío siempre se descarga."""
	version = None
	if not forzar and frappe.get_all("Contribuyente DGII", limit=1):
		version = frappe.db.get_single_value("Configuracion DGII", "padron_version_dgii")

	try:
		contenido, version = descargar_padron(version)
		total = importar_padron(contenido) if contenido else None
	except Exception:
		frappe.log_error(title="Padrón RNC DGII: error al sincronizar")
		raise

	valores = {"padron_ultima_verificacion": now_datetime()}
	if total is not None:
		valores.update(
			padron_ultima_sincronizacion=now_datetime(), padron_registros=total, padron_version_dgii=version
		)
	frappe.db.set_single_value("Configuracion DGII", valores)
	frappe.db.commit()
	return total


def encolar(forzar: bool = False):
	"""Pone la sincronización en la cola long (una sola a la vez). La tarea diaria de las 2:00 a. m.
	llama aquí sin `forzar`: solo descarga si la DGII publicó un archivo nuevo."""
	frappe.enqueue(
		"erpnext_rd.padron_rnc.padron.sincronizar_padron",
		queue="long",
		timeout=3600,
		job_id="erpnext_rd:sincronizar_padron",
		deduplicate=True,
		enqueue_after_commit=True,
		forzar=forzar,
	)


@frappe.whitelist()
def encolar_sincronizacion():
	frappe.only_for(("System Manager", "Accounts Manager"))
	encolar(forzar=True)
	return _("Sincronización del padrón en cola. Puede tardar algunos minutos.")


@frappe.whitelist()
def consultar_rnc(numero: str) -> dict | None:
	"""Busca un RNC / Cédula en el padrón. Usado para autocompletar clientes y proveedores."""
	numero = limpiar_identificacion(numero)
	if len(numero) not in (9, 11):
		return None
	return frappe.db.get_value(
		"Contribuyente DGII",
		numero,
		["rnc", "razon_social", "nombre_comercial", "actividad_economica", "estado", "regimen_pago"],
		as_dict=True,
	)
