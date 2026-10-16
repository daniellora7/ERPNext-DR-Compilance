"""Anticipos del ISR del año por período, con su vencimiento y la base del IR-2 usada."""

from erpnext_rd.dgii_reportes.anticipos import reporte


def execute(filters=None):
	return reporte(filters)
