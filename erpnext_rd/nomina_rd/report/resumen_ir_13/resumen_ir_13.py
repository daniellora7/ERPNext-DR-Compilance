"""Resumen IR-13: retenciones de ISR a asalariados del año."""

from erpnext_rd.nomina_rd.ir13 import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte(filters)
