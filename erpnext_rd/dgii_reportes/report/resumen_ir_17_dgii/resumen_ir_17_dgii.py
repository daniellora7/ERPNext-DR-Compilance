"""Resumen de apoyo para la declaración IR-17 (otras retenciones de ISR)."""

from erpnext_rd.dgii_reportes.declaraciones import reporte_ir17


def execute(filters=None):
	return reporte_ir17(filters)
