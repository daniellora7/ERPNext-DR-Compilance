"""Esquemas XSD oficiales del e-CF (DGII, versión 1.0) y el armado del XML guiado por ellos.

Los XSD de `xsd/` son los de la DGII (Documentación sobre e-CF → Documentación Técnica (XSD)). El XML
se arma recorriendo el esquema de cada tipo: de los datos (un dict anidado con los nombres de los
elementos) solo se emiten los elementos que ese tipo acepta y en el orden que el esquema exige. Así el
mismo código sirve para los diez tipos (E31 … E47), el resumen de factura de consumo (RFCE), la
aprobación comercial (ACECF), el acuse de recibo (ARECF) y la anulación de rangos (ANECF), y se
adapta solo cuando la DGII actualiza un esquema.

Reglas del armado:
- Un elemento simple se emite si tiene valor; si es obligatorio y no tiene, es un error (dice cuál).
- Un elemento compuesto se emite si alguno de sus hijos tiene datos o si es obligatorio.
- Un elemento repetible recibe una lista.
- La firma (`xs:any`, obligatoria al final) la agrega `firma.py`; por eso el XSD se valida ya firmado.
"""

import functools
import os

import frappe
from frappe import _
from lxml import etree

XS = "{http://www.w3.org/2001/XMLSchema}"
CARPETA = os.path.join(os.path.dirname(__file__), "xsd")
ARCHIVOS = {
	**{t: f"e{t}.xsd" for t in (31, 32, 33, 34, 41, 43, 44, 45, 46, 47)},
	"RFCE": "rfce32.xsd",
	# Aprobación comercial, acuse de recibo y anulación de rangos de e-NCF
	"ACECF": "acecf.xsd",
	"ARECF": "arecf.xsd",
	"ANECF": "anecf.xsd",
}


class FaltaDato(frappe.ValidationError):
	pass


# Arreglos al cargar (los archivos oficiales quedan intactos): libxml2, el validador de lxml, sigue el
# estándar XSD más estricto que el validador .NET con el que la DGII publica los esquemas.
# - Grupos sin captura «(?:…)» en los patrones (no existen en las expresiones regulares de XSD).
# - El e-CF 31 usa IndicadorServicioTodoIncluidoType sin definirlo; se toma la definición del e-CF 32.
TIPOS_FALTANTES = {
	"IndicadorServicioTodoIncluidoType": '<xs:simpleType name="IndicadorServicioTodoIncluidoType" '
	'xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:restriction base="xs:integer">'
	'<xs:enumeration value="1"/></xs:restriction></xs:simpleType>',
}


@functools.cache
def _arbol(tipo) -> etree._ElementTree:
	with open(os.path.join(CARPETA, ARCHIVOS[tipo]), "rb") as archivo:
		texto = archivo.read().replace(b"(?:", b"(")
	raiz = etree.fromstring(texto)
	definidos = {t.get("name") for t in raiz if isinstance(t.tag, str) and t.get("name")}
	usados = {e.get("type") for e in raiz.iter(XS + "element") if e.get("type")}
	for nombre in usados - definidos:
		if nombre in TIPOS_FALTANTES:
			raiz.append(etree.fromstring(TIPOS_FALTANTES[nombre]))
	return etree.ElementTree(raiz)


@functools.cache
def esquema(tipo) -> etree.XMLSchema:
	return etree.XMLSchema(_arbol(tipo))


def _tipos_con_nombre(tipo) -> dict:
	raiz = _arbol(tipo).getroot()
	return {t.get("name"): t for t in raiz if t.tag == XS + "complexType" and t.get("name")}


def _elementos(nodo):
	for hijo in nodo:
		if hijo.tag == XS + "element":
			yield hijo
		elif hijo.tag in (XS + "sequence", XS + "choice", XS + "all"):
			yield from _elementos(hijo)


def _hijos(definicion, nombrados):
	"""Elementos hijos (en orden) de un elemento compuesto, con tipo en línea o con nombre."""
	tipo = definicion.get("type")
	compuesto = nombrados[tipo] if tipo in nombrados else definicion.find(XS + "complexType")
	if compuesto is not None:
		yield from _elementos(compuesto)


def _es_compuesto(definicion, nombrados) -> bool:
	return definicion.find(XS + "complexType") is not None or definicion.get("type") in nombrados


def _vacio(valor) -> bool:
	return valor is None or valor == "" or valor == [] or valor == {}


def _con_datos(valor) -> bool:
	if isinstance(valor, dict):
		return any(_con_datos(v) for v in valor.values())
	if isinstance(valor, list):
		return any(_con_datos(v) for v in valor)
	return not _vacio(valor)


def _emitir(padre, definicion, valor, nombrados, ruta: str):
	nombre = definicion.get("name")
	obligatorio = definicion.get("minOccurs", "1") != "0"
	repetible = definicion.get("maxOccurs", "1") not in ("0", "1")
	valores = valor if repetible and isinstance(valor, list) else [valor]

	for v in valores:
		if _es_compuesto(definicion, nombrados):
			if not _con_datos(v) and not obligatorio:
				continue
			nodo = etree.SubElement(padre, nombre)
			datos = v if isinstance(v, dict) else {}
			for hijo in _hijos(definicion, nombrados):
				_emitir(nodo, hijo, datos.get(hijo.get("name")), nombrados, f"{ruta}/{hijo.get('name')}")
		else:
			if _vacio(v):
				if obligatorio:
					raise FaltaDato(_("Falta el dato obligatorio {0} del e-CF").format(ruta.lstrip("/")))
				continue
			etree.SubElement(padre, nombre).text = str(v)


def construir(tipo, datos: dict) -> etree._Element:
	"""XML (sin firmar) del tipo de e-CF (31 … 47) o "RFCE" a partir de los datos."""
	raiz_xsd = _arbol(tipo).getroot()
	nombrados = _tipos_con_nombre(tipo)
	elemento = next(e for e in raiz_xsd if e.tag == XS + "element")
	raiz = etree.Element(elemento.get("name"))
	for hijo in _hijos(elemento, nombrados):
		_emitir(raiz, hijo, datos.get(hijo.get("name")), nombrados, hijo.get("name"))
	return raiz


def errores(tipo, xml: bytes) -> list[str]:
	"""Errores del XML (ya firmado) frente al XSD oficial; vacío si es válido."""
	from erpnext_rd.ecf.firma import leer

	validador = esquema(tipo)
	if validador.validate(leer(xml)):
		return []
	return [f"{e.line}: {e.message}" for e in validador.error_log]


def validar(tipo, xml: bytes):
	if fallas := errores(tipo, xml):
		frappe.throw(
			"<br>".join(fallas[:10]), title=_("El e-CF no cumple el esquema de la DGII"), exc=FaltaDato
		)
