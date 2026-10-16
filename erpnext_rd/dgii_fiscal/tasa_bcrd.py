"""Tasa de cambio del dólar del Banco Central (BCRD) en el *Currency Exchange* de ERPNext.

El BCRD publica cada día laborable, al final de la tarde, la tasa de referencia del mercado spot
(compra y venta) en un Excel con todo el histórico (hoja «Diaria»: Año | Mes | Día | Compra | Venta).
La tarea programada lo descarga solo si cambió (If-Modified-Since) y crea el *Currency Exchange*
USD → DOP de cada día que falte. ERPNext toma el registro más reciente que no pase de la fecha del
documento, así que los fines de semana y feriados usan la tasa del último día laborable.

Nunca se modifica un *Currency Exchange* que ya exista para esa fecha (uno puesto a mano se respeta).
"""

import io
from datetime import date

import frappe
import requests
from frappe import _
from frappe.utils import add_years, getdate, now_datetime, today

URL_TASA_DOLAR = (
	"https://cdn.bancentral.gov.do/documents/estadisticas/mercado-cambiario/documents/"
	"TASA_DOLAR_REFERENCIA_MC.xlsx"
)
MESES = {
	"ene": 1,
	"feb": 2,
	"mar": 3,
	"abr": 4,
	"may": 5,
	"jun": 6,
	"jul": 7,
	"ago": 8,
	"sep": 9,
	"oct": 10,
	"nov": 11,
	"dic": 12,
}
COMPRA = "Compra"
VENTA = "Venta"
SEPARADA = "Compra en ventas, venta en compras"


def leer_tasas(contenido: bytes) -> dict[date, tuple[float, float]]:
	"""{fecha: (compra, venta)} de la hoja diaria del Excel del BCRD."""
	import openpyxl

	libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
	hoja = libro["Diaria"] if "Diaria" in libro.sheetnames else libro.worksheets[0]
	tasas = {}
	for fila in hoja.iter_rows(values_only=True):
		if len(fila) < 5:
			continue
		anio, mes, dia, compra, venta = fila[:5]
		mes = MESES.get(str(mes or "").strip().lower()[:3])
		if not (isinstance(anio, int | float) and mes and isinstance(dia, int | float)):
			continue
		if not (isinstance(compra, int | float) and isinstance(venta, int | float)) or compra <= 0:
			continue
		try:
			tasas[date(int(anio), mes, int(dia))] = (float(compra), float(venta))
		except ValueError:
			continue
	libro.close()
	return tasas


def descargar(version: str | None = None) -> tuple[bytes | None, str | None]:
	"""Descarga el Excel si el BCRD publicó uno distinto de `version` (su Last-Modified).

	Devuelve (contenido, versión); sin cambios, el contenido es None."""
	encabezados = {"User-Agent": "Mozilla/5.0 ERPNext-RD"}
	if version:
		encabezados["If-Modified-Since"] = version
	respuesta = requests.get(URL_TASA_DOLAR, timeout=120, headers=encabezados)
	if respuesta.status_code == 304:
		return None, version
	respuesta.raise_for_status()
	nueva = respuesta.headers.get("Last-Modified")
	if version and nueva == version:
		return None, version
	return respuesta.content, nueva


def registros(compra: float, venta: float, tipo: str) -> list[dict]:
	"""Los *Currency Exchange* de un día según el tipo de tasa elegido en Configuración DGII."""
	if tipo == SEPARADA:
		# Al vender en dólares la empresa los cambia al banco (compra); al pagar en dólares, los compra (venta)
		return [
			{"exchange_rate": compra, "for_selling": 1, "for_buying": 0},
			{"exchange_rate": venta, "for_selling": 0, "for_buying": 1},
		]
	return [{"exchange_rate": venta if tipo == VENTA else compra, "for_selling": 1, "for_buying": 1}]


def registrar_tasas(tasas: dict[date, tuple[float, float]], tipo: str, desde: date) -> int:
	"""Crea los *Currency Exchange* USD → DOP de las fechas desde `desde` que no tengan ninguno.
	Devuelve cuántas fechas se registraron."""
	existentes = set(
		frappe.get_all(
			"Currency Exchange",
			filters={"from_currency": "USD", "to_currency": "DOP", "date": (">=", desde)},
			pluck="date",
		)
	)
	nuevas = 0
	for fecha in sorted(f for f in tasas if f >= desde and f not in existentes):
		for valores in registros(*tasas[fecha], tipo):
			frappe.get_doc(
				{"doctype": "Currency Exchange", "date": fecha, "from_currency": "USD", "to_currency": "DOP"}
				| valores
			).insert(ignore_permissions=True)
		nuevas += 1
	return nuevas


def hay_empresas_en_pesos() -> bool:
	return bool(frappe.db.exists("Company", {"default_currency": "DOP"}))


def actualizar_tasa(forzar: bool = False) -> int | None:
	"""Registra las tasas del BCRD que falten. Devuelve las fechas nuevas, o None si no hubo cambios.

	La primera vez trae desde el 1 de enero del año anterior; después, desde la última registrada.
	`forzar` (botón de Configuración DGII) descarga aunque el archivo no haya cambiado."""
	conf = frappe.get_single("Configuracion DGII")
	if not forzar and not (conf.tasa_bcrd_activa and hay_empresas_en_pesos()):
		return None
	if not frappe.db.exists("Currency", "USD") or not frappe.db.exists("Currency", "DOP"):
		return None

	try:
		contenido, version = descargar(None if forzar else conf.tasa_bcrd_version)
		if not contenido:
			frappe.db.set_single_value("Configuracion DGII", "tasa_bcrd_ultima_verificacion", now_datetime())
			return None
		tasas = leer_tasas(contenido)
	except Exception:
		frappe.log_error(title="Tasa del Banco Central: error al descargar")
		raise
	if not tasas:
		frappe.log_error(title="Tasa del Banco Central: el archivo no trae tasas diarias")
		return None

	if conf.tasa_bcrd_ultima_fecha:
		desde = getdate(conf.tasa_bcrd_ultima_fecha)
	else:
		desde = date(getdate(add_years(today(), -1)).year, 1, 1)
	nuevas = registrar_tasas(tasas, conf.tasa_bcrd_tipo or COMPRA, desde)

	ultima = max(tasas)
	frappe.db.set_single_value(
		"Configuracion DGII",
		{
			"tasa_bcrd_ultima_fecha": ultima,
			"tasa_bcrd_compra": tasas[ultima][0],
			"tasa_bcrd_venta": tasas[ultima][1],
			"tasa_bcrd_version": version,
			"tasa_bcrd_ultima_verificacion": now_datetime(),
		},
	)
	return nuevas


def tarea_programada():
	"""Tarea de la mañana y de la tarde (el BCRD publica la del día al final de la tarde)."""
	try:
		actualizar_tasa()
	except Exception:
		# Ya quedó en el Error Log; se reintenta en la próxima corrida
		pass


@frappe.whitelist()
def actualizar_ahora() -> str:
	frappe.only_for(("System Manager", "Accounts Manager"))
	nuevas = actualizar_tasa(forzar=True)
	conf = frappe.get_single("Configuracion DGII")
	if not conf.tasa_bcrd_ultima_fecha:
		return _("No se pudo leer la tasa del Banco Central.")
	return _("Tasa del {0}: compra {1}, venta {2}. Días registrados: {3}.").format(
		frappe.format(conf.tasa_bcrd_ultima_fecha, {"fieldtype": "Date"}),
		conf.tasa_bcrd_compra,
		conf.tasa_bcrd_venta,
		nuevas or 0,
	)
