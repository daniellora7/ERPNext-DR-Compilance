"""Set de pruebas de la certificación e-CF (CerteCF).

La DGII entrega en el portal de certificación un archivo (Excel) con los e-CF que el emisor debe generar
y enviar: una fila por comprobante y una columna por elemento del XML, con el nombre del elemento del
XSD; las que se repiten llevan el número entre corchetes (`NombreItem[1]`, `FormaPago[2]`, y dos
índices si hay dos niveles repetidos). Aquí cada fila se convierte en los datos del e-CF recorriendo el
XSD de su tipo (la columna dice el elemento; el XSD, dónde va), se firma, se valida y queda un
*Envio ECF* del set; las facturas de consumo menores al monto del emisor llevan su resumen (RFCE).
"""

import datetime
import functools
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from erpnext_rd.ecf import datos, esquemas
from erpnext_rd.ecf.emision import ENVIO, emisor_de, enviar_a_dgii, registrar

XS = esquemas.XS
SET = "Set Pruebas ECF"
TIPOS = (31, 32, 33, 34, 41, 43, 44, 45, 46, 47)
VACIOS = ("", "#e", "#E")
COLUMNA = re.compile(r"\s*([A-Za-z][A-Za-z0-9]*)((?:\[\d+\])*)\s*")


def _formato(definicion, simples: dict):
	"""(base, decimales o ancho) del tipo simple de un elemento, para dar forma a los números de Excel."""
	tipo = definicion.find(XS + "simpleType")
	if tipo is None:
		tipo = simples.get(definicion.get("type"))
	restriccion = tipo.find(XS + "restriction") if tipo is not None else None
	if restriccion is None:
		return ("texto", 0)
	base = restriccion.get("base", "").split(":")[-1]
	if base in ("integer", "int", "long", "short", "byte"):
		return ("entero", 0)
	if base == "decimal":
		decimales = restriccion.find(XS + "fractionDigits")
		return ("decimal", cint(decimales.get("value")) if decimales is not None else 2)
	opciones = [e.get("value") for e in restriccion.findall(XS + "enumeration")]
	if opciones and all(o.isdigit() for o in opciones) and len({len(o) for o in opciones}) == 1:
		return ("texto", len(opciones[0]))  # códigos con ceros a la izquierda ("01")
	return ("texto", 0)


@functools.cache
def rutas(tipo) -> dict:
	"""Elemento simple → (camino desde la raíz [(nombre, repetible)], formato). Si un nombre se repite en
	el esquema se toma el primero en el orden del documento."""
	raiz = esquemas._arbol(tipo).getroot()
	nombrados = esquemas._tipos_con_nombre(tipo)
	simples = {t.get("name"): t for t in raiz if t.tag == XS + "simpleType"}
	resultado = {}

	def recorrer(definicion, camino):
		for hijo in esquemas._hijos(definicion, nombrados):
			paso = (hijo.get("name"), hijo.get("maxOccurs", "1") not in ("0", "1"))
			if esquemas._es_compuesto(hijo, nombrados):
				recorrer(hijo, (*camino, paso))
			else:
				resultado.setdefault(hijo.get("name"), ((*camino, paso), _formato(hijo, simples)))

	recorrer(next(e for e in raiz if e.tag == XS + "element"), ())
	return resultado


def valor(celda, formato) -> str | None:
	"""Texto del XML a partir de la celda (Excel da números y fechas; CSV, texto)."""
	if celda is None or (isinstance(celda, str) and celda.strip() in VACIOS):
		return None
	if isinstance(celda, datetime.datetime):
		return datos.fecha_hora(celda) if celda.time() != datetime.time() else datos.fecha(celda)
	if isinstance(celda, datetime.date):
		return datos.fecha(celda)
	tipo, detalle = formato
	if isinstance(celda, str) and (tipo != "texto" or detalle):
		# Números escritos como texto (CSV): misma forma que los de Excel
		try:
			celda = float(celda) if "." in str(celda) else int(str(celda).strip())
		except ValueError:
			return str(celda).strip()
	if isinstance(celda, int | float) and not isinstance(celda, bool):
		if tipo == "decimal":
			texto = f"{flt(celda, detalle):.{detalle}f}"
			return texto if detalle == 2 else (texto.rstrip("0").rstrip(".") or "0")
		if float(celda).is_integer():
			return str(int(celda)).zfill(detalle)
		return str(celda)
	return str(celda).strip()


def _limpiar(nodo):
	"""Quita las entradas vacías que dejan los índices salteados."""
	if isinstance(nodo, dict):
		return {k: _limpiar(v) for k, v in nodo.items()}
	if isinstance(nodo, list):
		return [_limpiar(v) for v in nodo if v not in ({}, None)]
	return nodo


def datos_de_fila(tipo, fila: dict) -> dict:
	"""Datos del e-CF (dict anidado de `esquemas.construir`) de una fila del set."""
	mapa = rutas(tipo)
	resultado = {}
	for columna, celda in fila.items():
		coincide = COLUMNA.fullmatch(str(columna or ""))
		if not coincide or coincide.group(1) not in mapa:
			continue
		camino, formato = mapa[coincide.group(1)]
		texto = valor(celda, formato)
		if texto is None:
			continue
		indices = [int(i) for i in re.findall(r"\d+", coincide.group(2))]
		nodo = resultado
		for posicion, (nombre, repetible) in enumerate(camino):
			ultimo = posicion == len(camino) - 1
			if repetible:
				numero = max(indices.pop(0) if indices else 1, 1)
				lista = nodo.setdefault(nombre, [])
				while len(lista) < numero:
					lista.append(None if ultimo else {})
				if ultimo:
					lista[numero - 1] = texto
				else:
					nodo = lista[numero - 1]
			elif ultimo:
				nodo[nombre] = texto
			else:
				nodo = nodo.setdefault(nombre, {})
	return _limpiar(resultado)


def leer_filas(file_url: str) -> list[dict]:
	"""Filas del archivo (primera fila: nombres de las columnas)."""
	if file_url.lower().endswith(".csv"):
		from frappe.utils.csvutils import read_csv_content

		archivo = frappe.get_doc("File", {"file_url": file_url})
		tabla = read_csv_content(archivo.get_content())
	else:
		from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

		tabla = read_xlsx_file_from_attached_file(file_url=file_url)
	if not tabla:
		return []
	encabezado = [str(c or "").strip() for c in tabla[0]]
	return [
		dict(zip(encabezado, fila, strict=False))
		for fila in tabla[1:]
		if any(c not in (None, "") for c in fila)
	]


def _envios(nombre: str, estados=None) -> list:
	filtros = {"tipo_documento": SET, "documento": nombre}
	if estados:
		filtros["estado"] = ("in", estados)
	return frappe.get_all(ENVIO, filters=filtros, fields=["name", "encf", "estado"], order_by="creation")


@frappe.whitelist(methods=["POST"])
def generar(name: str) -> dict:
	"""Firma los e-CF del set que todavía no tienen envío."""
	doc = frappe.get_doc(SET, name)
	doc.check_permission("write")
	emisor = emisor_de(doc.company)
	hechos = {e.encf for e in _envios(name)}
	errores = []
	for numero, fila in enumerate(leer_filas(doc.archivo), start=2):
		encf = str(fila.get("eNCF") or "").strip()
		if encf in hechos:
			continue
		try:
			tipo = cint(fila.get("TipoeCF"))
			if tipo not in TIPOS:
				raise ValueError(_("TipoeCF no válido: {0}").format(fila.get("TipoeCF")))
			contenido = datos_de_fila(tipo, fila)
			contenido.setdefault("Encabezado", {}).setdefault("Version", datos.VERSION)
			contenido.setdefault("FechaHoraFirma", datos.fecha_hora())
			total = flt(contenido.get("Encabezado", {}).get("Totales", {}).get("MontoTotal"))
			registrar(
				emisor,
				tipo,
				contenido,
				{"tipo_documento": SET, "documento": name, "fecha_firma": now_datetime()},
				es_rfce=tipo == 32 and total < flt(emisor.monto_rfce),
			)
			hechos.add(encf)
		except Exception as error:
			errores.append(f"{_('Fila')} {numero} ({encf or '?'}): {frappe.utils.strip_html(str(error))}")
	frappe.local.message_log = []  # los errores de cada fila van en el resultado, no en ventanas
	doc.generados = len(_envios(name))
	doc.resultado = "\n".join(errores)
	doc.estado = "Con errores" if errores else "Firmado"
	doc.save()
	return {"generados": doc.generados, "errores": len(errores)}


@frappe.whitelist(methods=["POST"])
def enviar(name: str) -> dict:
	"""Envía a la DGII los e-CF firmados del set (y reintenta los que dieron error)."""
	doc = frappe.get_doc(SET, name)
	doc.check_permission("write")
	ambiente = frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF"
	if ambiente == "eCF":
		frappe.throw(_("El set de pruebas no se envía en producción: cambie el ambiente a CerteCF."))
	emisor = emisor_de(doc.company)
	for fila in _envios(name, ("Firmado", "Error", "Contingencia")):
		enviar_a_dgii(frappe.get_doc(ENVIO, fila.name), emisor)
	doc.enviados = len([e for e in _envios(name) if e.estado != "Firmado"])
	doc.estado = "Enviado" if not doc.resultado else "Con errores"
	doc.save()
	return {"enviados": doc.enviados}
