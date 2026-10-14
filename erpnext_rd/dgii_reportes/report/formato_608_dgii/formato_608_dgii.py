"""Formato de envío 608 DGII: comprobantes anulados."""

from erpnext_rd.dgii_reportes.formatos import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte("608", filters)
