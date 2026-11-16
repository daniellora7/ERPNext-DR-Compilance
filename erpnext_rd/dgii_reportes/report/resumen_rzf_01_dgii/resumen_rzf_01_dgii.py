"""Apoyo para el RZF-01: ventas del mes de una zona franca industrial, por casilla."""

from erpnext_rd.dgii_reportes.rzf import reporte


def execute(filters=None):
	return reporte(filters)
