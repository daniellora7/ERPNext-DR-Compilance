"""Padrón de contribuyentes de la DGII: descarga, importación y consulta."""

import io
import time
import zipfile

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion

# Archivo público de la DGII (texto separado por "|", codificación latin-1):
# RNC|RAZÓN SOCIAL|NOMBRE COMERCIAL|ACTIVIDAD|...|...|...|...|FECHA INICIO|ESTADO|RÉGIMEN
URL_PADRON = "https://www.dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip"
LOTE = 5000


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


def descargar_padron(intentos: int = 4) -> bytes:
	"""Descarga el ZIP. El servidor de la DGII a veces corta la conexión: se reintenta."""
	for intento in range(1, intentos + 1):
		try:
			respuesta = requests.get(URL_PADRON, timeout=300, headers={"User-Agent": "Mozilla/5.0 ERPNext-RD"})
			respuesta.raise_for_status()
			zipfile.ZipFile(io.BytesIO(respuesta.content)).testzip()
			return respuesta.content
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


def sincronizar_padron():
	"""Tarea programada: descarga e importa el padrón completo (~800 mil registros)."""
	try:
		total = importar_padron(descargar_padron())
	except Exception:
		frappe.log_error(title="Padrón RNC DGII: error al sincronizar")
		raise

	frappe.db.set_single_value(
		"Configuracion DGII",
		{"padron_ultima_sincronizacion": now_datetime(), "padron_registros": total},
	)
	frappe.db.commit()
	return total


@frappe.whitelist()
def encolar_sincronizacion():
	frappe.only_for(("System Manager", "Accounts Manager"))
	frappe.enqueue(
		"erpnext_rd.padron_rnc.padron.sincronizar_padron",
		queue="long",
		timeout=3600,
		job_id="erpnext_rd:sincronizar_padron",
		deduplicate=True,
	)
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
