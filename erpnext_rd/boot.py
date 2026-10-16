import frappe
from frappe import _

PAIS = "Dominican Republic"
DOCTYPES_FACTURA = ("Sales Invoice", "POS Invoice")


def boot_session(bootinfo):
	traducir_dock(bootinfo)
	formatos_por_empresa(bootinfo)


def formatos_por_empresa(bootinfo):
	"""Formato de impresión de las facturas de cada empresa (`frappe.boot.rd_formatos`).

	El formato fiscal de la app es el predeterminado del DocType, pero no aplica a empresas de otros
	países: esas usan el estándar de Frappe, salvo que la empresa indique otro en *Formato de impresión
	de facturas*. El formulario y la vista de impresión lo toman de aquí (public/js/invoice_dgii.js y
	public/js/print_view.js)."""
	if frappe.session.user == "Guest":
		return
	from erpnext_rd.formatos import FISCALES

	fiscales = {f["name"] for f in FISCALES}
	empresas = frappe.get_all("Company", fields=["name", "country", "rd_formato_factura"])
	resultado = {}
	for doctype in DOCTYPES_FACTURA:
		if not frappe.db.exists("DocType", doctype):
			continue
		defecto = frappe.get_meta(doctype).default_print_format or "Standard"
		por_empresa = {}
		for e in empresas:
			if doctype == "Sales Invoice" and e.rd_formato_factura:
				por_empresa[e.name] = e.rd_formato_factura
			elif e.country != PAIS and defecto in fiscales:
				por_empresa[e.name] = "Standard"
			else:
				por_empresa[e.name] = defecto
		resultado[doctype] = {"defecto": defecto, "empresas": por_empresa}
	bootinfo.rd_formatos = resultado


def traducir_dock(bootinfo):
	"""Traduce los nombres del dock al idioma del usuario.

	El dock de Frappe v16 muestra el título guardado de cada entrada sin pasarlo por `__()`, así que
	"Accounts" o "Payroll" salen en inglés aunque exista la traducción. Se traducen aquí, en la sesión
	de cada usuario, sin escribir nada en la base. Al guardar "Organizar dock", Frappe reconoce el
	título traducido como heredado (`settle_reference`) y no lo guarda como propio.
	"""
	for filas in (bootinfo.get("dock") or {}).values():
		_traducir_titulos(filas)
	for app in bootinfo.get("app_data") or []:
		_traducir_titulos(app.get("dock"))


def _traducir_titulos(filas):
	for fila in filas or []:
		if isinstance(fila, dict) and fila.get("title"):
			fila["title"] = _(fila["title"])
