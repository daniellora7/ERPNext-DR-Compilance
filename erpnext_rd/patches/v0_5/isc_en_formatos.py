"""Fase 8.2: el ISC en la factura y el recibo POS (columna y fila propias, aparte del ITBIS).

Solo cambia los bloques que siguen como los dejó la versión anterior; los editados se respetan.
"""

from erpnext_rd import formatos

# Huellas (formatos.huella) de los bloques de la versión 0.5.5
ANTERIORES = {
	"Factura Fiscal RD": {
		"detalle": {"fa8ea9e6f06557f3d0d9ccad6ddd7eaf1480b787d057a3949a96ec3fa4fe40ac"},
		"totales": {"245b3b8f96c0e36c0cfbca65af048a46cf7589e01607abeb0f6df3e70dfd4db9"},
	},
	"Recibo POS RD": {"totales": {"22fa243e3f5eaafa6c9bc085fbde32ba6f7926a755d3544242c97d9e0f8d19a5"}},
	"Recibo POS RD (POS Invoice)": {
		"totales": {"22fa243e3f5eaafa6c9bc085fbde32ba6f7926a755d3544242c97d9e0f8d19a5"}
	},
}


def execute():
	for formato in formatos.FISCALES:
		if formato["name"] in ANTERIORES:
			formatos.actualizar_bloques(formato, ANTERIORES[formato["name"]])
