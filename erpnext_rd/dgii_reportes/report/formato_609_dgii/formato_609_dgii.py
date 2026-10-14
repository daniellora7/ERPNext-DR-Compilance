"""Formato de envío 609 DGII: pagos al exterior."""

from erpnext_rd.dgii_reportes.formatos import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte("609", filters)
