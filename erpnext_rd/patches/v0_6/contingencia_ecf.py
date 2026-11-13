"""e-CF: plazos de contingencia en Configuracion DGII y la leyenda de contingencia en la factura y el
recibo POS impresos (Instructivo de Contingencia de FE de la DGII).

Los valores por defecto de un DocType single no llegan solos a un sitio existente. Los bloques impresos
solo cambian si siguen como los dejó la versión anterior; los editados se respetan.
"""

import frappe

from erpnext_rd import formatos

CONFIG = "Configuracion DGII"
PLAZOS = {"horas_contingencia_ecf": 72, "dias_contingencia_ncf": 15, "dias_reemplazo_contingencia": 30}

# Huellas (formatos.huella) del bloque «ecf» de la versión 0.6.0
FACTURA = {"ecf": {"992d87dd42b485c8f75e51bfc5e42feabad6fa0b19ad34dd3fbf71abc351f7bd"}}
RECIBO = {"ecf": {"3ee25a58ec6707d5e487e0f4cb40405f57a259d3459bc3642ee520ee2b1d967c"}}
ANTERIORES = {
	"Factura Fiscal RD": FACTURA,
	"Recibo POS RD": RECIBO,
	"Recibo POS RD (POS Invoice)": RECIBO,
}


def execute():
	for campo, valor in PLAZOS.items():
		if not frappe.db.get_single_value(CONFIG, campo):
			frappe.db.set_single_value(CONFIG, campo, valor)
	for formato in formatos.FISCALES:
		if formato["name"] in ANTERIORES:
			formatos.actualizar_bloques(formato, ANTERIORES[formato["name"]])
