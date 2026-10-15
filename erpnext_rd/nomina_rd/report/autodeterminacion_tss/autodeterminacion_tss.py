"""Archivo de autodeterminación mensual de la TSS (SUIR Plus)."""

from erpnext_rd.nomina_rd.tss import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte(filters)
