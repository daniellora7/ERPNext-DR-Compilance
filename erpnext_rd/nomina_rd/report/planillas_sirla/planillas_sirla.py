"""Planillas del Ministerio de Trabajo para el SIRLA (DGT-3 y DGT-4)."""

from erpnext_rd.nomina_rd.sirla import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte(filters)
