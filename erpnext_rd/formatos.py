"""Formatos de impresión de la app, editables en el constructor de formatos de Frappe.

Cada formato se guarda como *Print Format* no estándar hecho con el constructor de formatos de Frappe
(Print Format Builder): una sección por bloque (encabezado, cliente, detalle, totales...), cada una con
un bloque HTML (Jinja) que se puede editar, mover o quitar, y los estilos en el CSS del formato. También
se le pueden agregar campos del documento desde el constructor. Las plantillas de `templates/print/`
son solo el contenido inicial:

- Si el formato no existe, se crea.
- Si existe como lo dejaban versiones anteriores de la app (estándar o con un `{% include %}` a una
  plantilla), se convierte al constructor.
- Si ya está en el constructor o el usuario lo editó, no se toca.

Cada bloque toma sus datos de los métodos Jinja de la app (`rd_datos_fiscales`, `rd_datos_volante`),
que se calculan una sola vez por documento (`por_documento`). El PDF de estos formatos lo genera el
motor Chrome de Frappe (la imagen Docker trae Chromium; ver deploy/Containerfile).
"""

import functools
import json

import frappe

FISCALES = [
	{
		"name": "Factura Fiscal RD",
		"doc_type": "Sales Invoice",
		"carpeta": "factura_rd",
		"margen": 12,
		"bloques": [
			("Encabezado fiscal (empresa y NCF)", "encabezado"),
			("Cliente", "cliente"),
			("Detalle de la factura", "detalle"),
			("Totales", "totales"),
			("Comprobante electrónico (QR)", "ecf"),
			("Términos y condiciones", "terminos"),
		],
	},
	{
		"name": "Recibo POS RD",
		"doc_type": "Sales Invoice",
		"carpeta": "recibo_pos_rd",
		"margen": 2,
		"bloques": [
			("Emisor", "emisor"),
			("Comprobante y cliente", "comprobante"),
			("Detalle", "detalle"),
			("Totales y pagos", "totales"),
			("Comprobante electrónico (QR)", "ecf"),
			("Pie", "pie"),
		],
	},
]
FISCALES.append({**FISCALES[1], "name": "Recibo POS RD (POS Invoice)", "doc_type": "POS Invoice"})
MODULO_FISCAL = "DGII Fiscal"


def por_documento(funcion):
	"""Guarda el resultado por documento durante la petición: cada bloque del formato lo vuelve a pedir."""

	@functools.wraps(funcion)
	def envoltura(doc):
		cache = getattr(frappe.local, "rd_datos_impresion", None)
		if cache is None:
			cache = frappe.local.rd_datos_impresion = {}
		clave = (funcion.__name__, doc.doctype, doc.name or id(doc), str(doc.get("modified")), doc.docstatus)
		if clave not in cache:
			cache[clave] = funcion(doc)
		return cache[clave]

	return envoltura


def _leer(carpeta: str, archivo: str) -> str:
	with open(
		frappe.get_app_path("erpnext_rd", "templates", "print", carpeta, archivo), encoding="utf8"
	) as f:
		return f.read()


def disenio(formato: dict) -> dict:
	"""Diseño del constructor de formatos: una sección por bloque HTML, sin encabezado ni pie de página."""
	secciones = []
	for i, (etiqueta, archivo) in enumerate(formato["bloques"], start=1):
		bloque = {
			"label": etiqueta,
			"fieldname": f"custom_html_{i}",
			"fieldtype": "HTML",
			"html": _leer(formato["carpeta"], f"{archivo}.html"),
			"custom": 1,
		}
		secciones.append({"label": "", "columns": [{"label": "", "fields": [bloque]}]})
	return {
		"header": {"columns": [{"label": "", "fields": []}]},
		"sections": secciones,
		"footer": {"columns": [{"label": "", "fields": []}]},
	}


def valores(formato: dict, modulo: str) -> dict:
	margen = formato.get("margen", 12)
	return {
		"doc_type": formato["doc_type"],
		"module": modulo,
		"standard": "No",
		"print_format_for": "DocType",
		"print_format_type": "Jinja",
		"custom_format": 0,
		"print_format_builder": 0,
		"print_format_builder_beta": 1,
		"format_data": json.dumps(disenio(formato), indent=1, ensure_ascii=False),
		"css": _leer(formato["carpeta"], "estilos.css"),
		"html": "",
		"pdf_generator": "chrome",
		"default_print_language": "es",
		"font_size": 11,
		"page_number": "Hide",
		"margin_top": margen,
		"margin_bottom": margen,
		"margin_left": margen,
		"margin_right": margen,
	}


def _de_version_anterior(actual) -> bool:
	"""Estándar o con el `{% include %}` de las versiones anteriores de la app (nunca editado)."""
	html = (actual.html or "").strip()
	return actual.standard == "Yes" or (actual.custom_format and (not html or html.startswith("{% include")))


def asegurar(formato: dict, modulo: str):
	"""Crea el formato en el constructor o convierte el de una versión anterior; no toca uno editado."""
	if not frappe.db.exists("DocType", formato["doc_type"]):
		return
	actual = frappe.db.get_value(
		"Print Format", formato["name"], ["standard", "html", "custom_format"], as_dict=True
	)
	if not actual:
		frappe.get_doc(
			{"doctype": "Print Format", "name": formato["name"], **valores(formato, modulo)}
		).insert(ignore_permissions=True)
	elif _de_version_anterior(actual):
		# Un formato estándar no se puede guardar fuera del modo desarrollador: se actualiza directo
		frappe.db.set_value("Print Format", formato["name"], valores(formato, modulo))
		frappe.clear_document_cache("Print Format", formato["name"])


def asegurar_fiscales():
	for formato in FISCALES:
		asegurar(formato, MODULO_FISCAL)
