# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

TABLA = "tabContribuyente DGII"
# Índice de texto completo para buscar palabras sueltas del nombre (padron.buscar_por_palabras)
INDICE_TEXTO = "busqueda_nombre"
COLUMNAS_TEXTO = ("razon_social", "nombre_comercial")


class ContribuyenteDGII(Document):
	pass


def on_doctype_update():
	# Frappe no crea índices FULLTEXT desde el JSON del DocType
	if not frappe.db.has_index(TABLA, INDICE_TEXTO):
		columnas = ", ".join(f"`{c}`" for c in COLUMNAS_TEXTO)
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLA}` ADD FULLTEXT INDEX `{INDICE_TEXTO}` ({columnas})")
