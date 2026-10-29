"""Índice FULLTEXT del padrón en los sitios que ya existían (en los nuevos lo crea on_doctype_update)."""

from erpnext_rd.padron_rnc.doctype.contribuyente_dgii.contribuyente_dgii import on_doctype_update


def execute():
	on_doctype_update()
