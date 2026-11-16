"""Fase 8.5: la liquidación del cuadre IR-2 impresa con el impuesto sobre los activos (IR-2-c2).

Solo cambia el bloque si sigue como lo dejó una versión anterior; uno editado se respeta.
"""

from erpnext_rd import formatos
from erpnext_rd.dgii_reportes import ir2

# Huellas (formatos.huella) del bloque «liquidacion» de las versiones 0.5.5 y 0.6.0
ANTERIORES = {
	"liquidacion": {
		"fcb9ed20db386e3e4f17a260e6c171ffa8c100dba7328a93dca274195a851b78",
		"ce5806d01425aceb789c0b18cde506fb897a177959dbf3d8b7fc9b3e63389f4d",
	}
}


def execute():
	formatos.actualizar_bloques(ir2.FORMATO, ANTERIORES)
