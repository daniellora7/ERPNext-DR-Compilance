"""Formato de envío 606 DGII: compras de bienes y servicios."""

from erpnext_rd.dgii_reportes.formatos import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte("606", filters)
