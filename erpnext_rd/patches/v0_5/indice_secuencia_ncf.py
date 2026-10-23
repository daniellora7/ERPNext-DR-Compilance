"""Índice de Secuencia NCF en los sitios que ya existían (en los nuevos lo crea on_doctype_update)."""

from erpnext_rd.dgii_fiscal.doctype.secuencia_ncf.secuencia_ncf import on_doctype_update


def execute():
	on_doctype_update()
