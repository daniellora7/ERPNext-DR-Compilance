"""Resumen IR-3: retenciones de ISR a asalariados del mes."""

from erpnext_rd.nomina_rd.ir3 import ejecutar_reporte


def execute(filters=None):
	return ejecutar_reporte(filters)
