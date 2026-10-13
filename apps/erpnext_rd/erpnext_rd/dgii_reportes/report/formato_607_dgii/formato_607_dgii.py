"""Formato de envío 607 DGII: ventas de bienes y servicios."""

from erpnext_rd.dgii_reportes.formatos import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte("607", filters)
