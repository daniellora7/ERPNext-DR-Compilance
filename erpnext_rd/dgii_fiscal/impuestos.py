"""Clasificación de impuestos por concepto fiscal DGII (columnas del 606 / 607).

El concepto sale del campo `rd_concepto_fiscal` de la cuenta (lo trae el catálogo DGII).
Si la cuenta no lo tiene, se deduce de su nombre (ITBIS, ISR, selectivo, propina).
"""

import frappe
from frappe.utils import flt

from erpnext_rd.dgii_fiscal import catalogos as cat

CATEGORIAS_COSTO = ("Valuation", "Valuation and Total")


def concepto_de_cuenta(cuenta: str | None, retencion: bool = False, de_terceros: bool = False) -> str | None:
	"""Concepto fiscal de una cuenta.

	`retencion`: la fila descuenta (retención). `de_terceros`: la retención la hizo el cliente.
	"""
	if not cuenta:
		return None
	datos = frappe.get_cached_value("Account", cuenta, ["rd_concepto_fiscal", "account_name"], as_dict=True)
	if not datos:
		return None
	if datos.rd_concepto_fiscal:
		return datos.rd_concepto_fiscal

	nombre = (datos.account_name or "").upper()
	if "PROPINA" in nombre:
		return cat.PROPINA_LEGAL
	if "SELECTIVO" in nombre or "ISC" in nombre.split():
		return cat.ISC
	es_isr = "ISR" in nombre or "RENTA" in nombre
	es_itbis = "ITBIS" in nombre
	if retencion or "RETEN" in nombre:
		if es_isr:
			return cat.ISR_RETENIDO_POR_TERCEROS if de_terceros else cat.ISR_RETENIDO
		if es_itbis:
			return cat.ITBIS_RETENIDO_POR_TERCEROS if de_terceros else cat.ITBIS_RETENIDO
	if es_itbis:
		return cat.ITBIS
	return cat.OTROS_IMPUESTOS


def montos_impuestos(doc) -> frappe._dict:
	"""Montos de impuestos de una factura (moneda de la empresa, siempre positivos)."""
	montos = frappe._dict(
		itbis=0.0,
		itbis_costo=0.0,
		itbis_retenido=0.0,
		isr_retenido=0.0,
		isc=0.0,
		propina=0.0,
		otros=0.0,
	)
	for fila in doc.get("taxes") or []:
		monto = abs(flt(fila.get("base_tax_amount_after_discount_amount") or fila.get("base_tax_amount")))
		if not monto:
			continue
		deducir = fila.get("add_deduct_tax") == "Deduct"
		concepto = concepto_de_cuenta(fila.account_head, retencion=deducir)

		if concepto == cat.ITBIS and not deducir:
			montos.itbis += monto
			if fila.get("category") in CATEGORIAS_COSTO:
				montos.itbis_costo += monto
		elif concepto == cat.ITBIS_RETENIDO or (concepto == cat.ITBIS and deducir):
			montos.itbis_retenido += monto
		elif concepto == cat.ISR_RETENIDO:
			montos.isr_retenido += monto
		elif concepto == cat.ISC:
			montos.isc += monto
		elif concepto == cat.PROPINA_LEGAL:
			montos.propina += monto
		elif concepto not in (cat.ITBIS_RETENIDO_POR_TERCEROS, cat.ISR_RETENIDO_POR_TERCEROS):
			montos.otros += monto
	return montos


def tipo_desde_cuentas(doc, campo_item: str, campo_cuenta: str) -> str | None:
	"""Tipo 606 / 607 sugerido por la cuenta de gasto o de ingreso de la línea de mayor monto."""
	lineas = sorted(doc.get("items") or [], key=lambda d: flt(d.get("base_net_amount")), reverse=True)
	for linea in lineas:
		cuenta = linea.get(campo_item)
		if cuenta:
			tipo = frappe.get_cached_value("Account", cuenta, campo_cuenta)
			if tipo:
				return tipo
	return None
