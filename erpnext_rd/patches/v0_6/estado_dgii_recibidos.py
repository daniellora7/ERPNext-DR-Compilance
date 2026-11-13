"""e-CF recibidos antes de la verificación con la DGII: quedan «Pendiente» los de los últimos días
(la tarea programada los consulta) y «Sin verificar» los demás y los no recibidos."""

import frappe
from frappe.query_builder import DocType
from frappe.utils import add_days, now_datetime

from erpnext_rd.ecf.recepcion import DIAS_VERIFICACION, RECIBIDO


def execute():
	r = DocType(RECIBIDO)
	sin_estado = r.estado_dgii.isnull() | (r.estado_dgii == "") | (r.estado_dgii == "Pendiente")
	recientes = r.fecha_recepcion >= add_days(now_datetime(), -DIAS_VERIFICACION)
	(
		frappe.qb.update(r)
		.set(r.estado_dgii, "Sin verificar")
		.where(sin_estado & ((r.estado != "Recibido") | ~recientes | r.fecha_recepcion.isnull()))
	).run()
	frappe.qb.update(r).set(r.estado_dgii, "Pendiente").where(
		sin_estado & (r.estado == "Recibido") & recientes
	).run()
