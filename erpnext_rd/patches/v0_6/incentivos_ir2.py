"""Fase 8.6: la liquidación del cuadre IR-2 impresa con las casillas de incentivos (3, 4, 10, 15, 16 y 20).

Solo cambia el bloque si sigue como lo dejó la versión anterior; uno editado se respeta.
"""

from erpnext_rd import formatos
from erpnext_rd.dgii_reportes import ir2

# Huella (formatos.huella) del bloque «liquidacion» de la versión 0.5.5
ANTERIORES = {"liquidacion": {"fcb9ed20db386e3e4f17a260e6c171ffa8c100dba7328a93dca274195a851b78"}}


def execute():
	formatos.actualizar_bloques(ir2.FORMATO, ANTERIORES)
