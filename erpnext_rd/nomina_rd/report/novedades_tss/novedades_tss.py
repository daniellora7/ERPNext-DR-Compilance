"""Archivo de novedades del período (NV) de la TSS."""

from erpnext_rd.nomina_rd.novedades import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte(filters)
