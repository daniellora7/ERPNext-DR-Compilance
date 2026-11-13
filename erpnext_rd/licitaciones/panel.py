"""Bloque de licitaciones del Panel RD Compliance (Fases 10.4 y 10.5).

Solo lee, con los mismos cálculos del reporte *Ofertas Estado* y de las alertas diarias.
"""

import frappe
from frappe.utils import add_days, cint, getdate, now_datetime

from erpnext_rd.licitaciones import alertas, ofertas, procesos, proveedor
from erpnext_rd.licitaciones.report.ofertas_estado import ofertas_estado

MAXIMO = 10
# Procesos nuevos: publicados en los últimos días y que aún reciben ofertas
DIAS_NUEVOS = 7


def resumen(company: str) -> dict | None:
	"""None si la empresa no vende al Estado o el usuario no ve las oportunidades."""
	if not frappe.db.exists(proveedor.DOCTYPE, {"company": company, "habilitado": 1}):
		return None
	if not frappe.has_permission(ofertas.DOCTYPE, "read"):
		return None
	conf = ofertas.configuracion()
	ahora = now_datetime()

	abiertas = ofertas_estado.datos(frappe._dict(company=company))
	con_oferta = set(
		frappe.get_all(
			ofertas.DOCTYPE,
			filters={"company": company, "rd_proceso_dgcp": ("is", "set")},
			pluck="rd_proceso_dgcp",
		)
	)
	nuevos = []
	if frappe.has_permission(procesos.DOCTYPE, "read"):
		nuevos = [
			p
			for p in alertas.de_la_empresa(
				company,
				{
					"estado_proceso": alertas.PUBLICADO,
					"creation": (">=", add_days(ahora, -DIAS_NUEVOS)),
					"fecha_fin_recepcion_ofertas": (">", ahora),
				},
			)
			if p.name not in con_oferta
		]
	dias_garantias = cint(conf.dias_aviso_garantias)
	garantias = (
		ofertas.garantias_por_vencer(company, getdate(ahora), dias_garantias) if dias_garantias else []
	)
	return {
		"ofertas": abiertas[:MAXIMO],
		"total_ofertas": len(abiertas),
		"nuevos": [
			{
				"name": p.name,
				"titulo": p.titulo,
				"institucion": p.unidad_compra,
				"monto": p.monto_estimado,
				"moneda": p.divisa,
				"cierre": p.fecha_fin_recepcion_ofertas,
			}
			for p in nuevos[:MAXIMO]
		],
		"total_nuevos": len(nuevos),
		"garantias": [
			{
				"oportunidad": g.parent,
				"tipo": g.tipo,
				"monto": g.monto,
				"moneda": g.currency,
				"vence": g.vigencia_hasta,
				"emisor": g.emisor,
			}
			for g in garantias[:MAXIMO]
		],
		"dias_aviso_cierre": cint(conf.dias_aviso_cierre),
		"ultima_sincronizacion": conf.ultima_sincronizacion,
	}
