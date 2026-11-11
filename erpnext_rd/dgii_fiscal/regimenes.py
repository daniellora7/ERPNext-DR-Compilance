"""Ventas a clientes de regímenes especiales (Fase 8.4): zonas francas y otros regímenes.

Base (confirmada en los textos de la DGII, 2026-11-11):
- Norma General 05-2019 (vigente desde el 8 de abril de 2019; guía informativa de la DGII): el
  comprobante para Regímenes Especiales (B14, electrónico E44) se usa para vender bienes o servicios
  exentos del ITBIS o el ISC a quienes están acogidos a regímenes especiales por ley, contrato o
  convenio ratificado por el Congreso, cuando el mercado local factura a una zona franca y entre
  zonas francas. La factura no lleva ITBIS ni ISC; el comprador debe tener al día la documentación.
- Consulta DGII G. L. 2817XXX (2022): una zona franca de la Ley 8-90 compra sin ITBIS los bienes y
  servicios para sus operaciones solo si presenta el Carnet de Acreditación de Regímenes Especiales
  actualizado (Código Tributario art. 357, Decreto 293-11 art. 16, Ley 8-90 art. 24 literal g).
- Consulta DGII G. L. 4398XXX (2024): las ventas de mercancías a zonas francas comerciales se tratan
  como exportación (tasa cero de ITBIS, sin ISC) si el suplidor conserva la licencia de la DGA y el
  Formulario Único de Exportación. Lo que la zona franca comercial compra para operar sí lleva ITBIS.
  La consulta no dice qué comprobante usar: aquí no se cambia el comprobante ni los impuestos.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta

ZONA_FRANCA = "Zona franca (Ley 8-90)"
ZONA_FRANCA_COMERCIAL = "Zona franca comercial"
OTRO_REGIMEN = "Otro régimen especial"
REGIMENES = (ZONA_FRANCA, ZONA_FRANCA_COMERCIAL, OTRO_REGIMEN)
# Los que compran con B14 / E44 sin ITBIS ni ISC
CON_COMPROBANTE_ESPECIAL = (ZONA_FRANCA, OTRO_REGIMEN)
TIPOS_ESPECIALES = ("B14", "E44")


def regimen_del_cliente(customer: str | None) -> frappe._dict:
	if not customer:
		return frappe._dict()
	return (
		frappe.db.get_value(
			"Customer",
			customer,
			["rd_regimen_especial", "rd_carnet_regimen", "rd_carnet_vence"],
			as_dict=True,
		)
		or frappe._dict()
	)


def tipo_especial(serie: str) -> str:
	return "E44" if serie == "E" else "B14"


def _tipo_de_la_venta(doc) -> str | None:
	from erpnext_rd.dgii_fiscal import ncf

	if doc.rd_tipo_comprobante:
		return doc.rd_tipo_comprobante
	if doc.is_return or doc.get("is_debit_note"):
		return None
	return ncf.tipo_por_defecto_venta(doc)


def es_venta_exenta(doc) -> bool:
	"""Venta con B14 / E44: sin ITBIS ni ISC."""
	return _tipo_de_la_venta(doc) in TIPOS_ESPECIALES


def _es_itbis(fila) -> bool:
	return concepto_de_cuenta(fila.account_head) == cat.ITBIS


def antes_de_validar(doc, method=None):
	"""doc_events before_validate (ventas), antes del ISC: quita las filas de ITBIS de una venta con B14 / E44."""
	from erpnext_rd.dgii_fiscal.ncf import _no_aplica, es_empresa_rd

	if not es_empresa_rd(doc.company) or _no_aplica(doc) or not es_venta_exenta(doc):
		return
	if not doc.get("taxes") and doc.get("taxes_and_charges"):
		doc.append_taxes_from_master()
	quitadas = [f for f in doc.get("taxes") or [] if _es_itbis(f)]
	if not quitadas:
		return
	doc.set("taxes", [f for f in doc.taxes if not _es_itbis(f)])
	for i, fila in enumerate(doc.taxes, start=1):
		fila.idx = i
	doc.taxes_and_charges = None
	frappe.msgprint(
		_("Venta a un régimen especial (comprobante {0}): se quitó el ITBIS (Norma General 05-2019).").format(
			_tipo_de_la_venta(doc)
		),
		indicator="blue",
		alert=True,
	)


def validar_venta(doc, tipo):
	"""Desde ncf.validar_venta: B14 / E44 solo a clientes de regímenes especiales con su carnet vigente."""
	if tipo.name not in TIPOS_ESPECIALES or doc.is_return or doc.get("is_debit_note"):
		return
	cliente = regimen_del_cliente(doc.customer)
	if cliente.rd_regimen_especial not in CON_COMPROBANTE_ESPECIAL:
		frappe.throw(
			_(
				"El comprobante {0} es para clientes acogidos a regímenes especiales (zonas francas y otros). "
				"Indique el régimen especial en el cliente {1} o use otro comprobante."
			).format(tipo.name, doc.customer),
			title=_("Régimen especial"),
		)
	if not cliente.rd_carnet_regimen:
		frappe.throw(
			_(
				"Registre en el cliente {0} el número del Carnet de Acreditación de Regímenes Especiales (o el "
				"documento que avala la exención) antes de facturar sin ITBIS."
			).format(doc.customer),
			title=_("Régimen especial"),
		)
	fecha = getdate(doc.get("posting_date") or frappe.utils.today())
	if cliente.rd_carnet_vence and getdate(cliente.rd_carnet_vence) < fecha:
		frappe.throw(
			_(
				"El carnet de régimen especial del cliente {0} venció el {1}: pida el carnet actualizado."
			).format(doc.customer, frappe.format(cliente.rd_carnet_vence, "Date")),
			title=_("Régimen especial"),
		)
	con_impuesto = [
		f.description or f.account_head
		for f in doc.get("taxes") or []
		if concepto_de_cuenta(f.account_head) in (cat.ITBIS, cat.ISC) and abs(f.tax_amount or 0) > 0.005
	]
	if con_impuesto:
		frappe.throw(
			_("La venta con {0} no lleva ITBIS ni ISC. Quite: {1}.").format(
				tipo.name, ", ".join(con_impuesto)
			),
			title=_("Régimen especial"),
		)
