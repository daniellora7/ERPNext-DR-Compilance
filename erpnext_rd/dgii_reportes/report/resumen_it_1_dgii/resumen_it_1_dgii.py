"""Resumen de apoyo para la declaración IT-1 (ITBIS)."""

from erpnext_rd.dgii_reportes.declaraciones import reporte_it1


def execute(filters=None):
	return reporte_it1(filters)
