"""Ley 30-26: escala del ISR de asalariados desde 2027 (exento hasta RD$480,000, tramo de 27%).

La tabla de la escala ahora tiene una escala por año. Las filas que ya existían (sin año) son la escala
que regía hasta ahora: quedan como la de 2026. Se agrega la de 2027 si el usuario no puso una.
"""

import frappe
from frappe.utils import cint

from erpnext_rd.install import agregar_escala_isr
from erpnext_rd.nomina_rd.calculos import ESCALA_ISR_2027


def execute():
	conf = frappe.get_single("Configuracion Nomina RD")
	if not conf.escala_isr:
		return  # sitio nuevo: after_migrate carga todas las escalas
	for tramo in conf.escala_isr:
		if not cint(tramo.anio):
			tramo.anio = 2026
	if not any(cint(t.anio) >= 2027 for t in conf.escala_isr):
		agregar_escala_isr(conf, 2027, ESCALA_ISR_2027)
	conf.save(ignore_permissions=True)
