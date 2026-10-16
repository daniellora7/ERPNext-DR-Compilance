"""Anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2 por casilla."""

from erpnext_rd.dgii_reportes.estados_ir2 import reporte


def execute(filters=None):
	return reporte(filters)
