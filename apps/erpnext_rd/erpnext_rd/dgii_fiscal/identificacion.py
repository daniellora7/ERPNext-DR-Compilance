"""Validación de RNC / Cédula en clientes y proveedores."""

import re

import frappe
from frappe import _

from erpnext_rd.dgii_fiscal.validaciones import (
	es_cedula_valida,
	es_rnc_valido,
	limpiar_identificacion,
	tipo_identificacion,
)


def existe_en_padron(numero: str) -> bool:
	return bool(frappe.db.exists("Contribuyente DGII", limpiar_identificacion(numero)))


def identificacion_valida(numero: str | None, tipo: str | None = None) -> bool:
	"""RNC o Cédula con dígito verificador correcto, o presente en el padrón DGII si así se configura."""
	numero = limpiar_identificacion(numero)
	tipo = tipo or tipo_identificacion(numero)

	if tipo == "RNC" and es_rnc_valido(numero):
		return True
	if tipo == "Cédula" and es_cedula_valida(numero):
		return True

	if tipo in ("RNC", "Cédula") and frappe.db.get_single_value(
		"Configuracion DGII", "validar_contra_padron"
	):
		return existe_en_padron(numero)

	return False


def validar_party(doc, method=None):
	"""doc_events: Company / Customer / Supplier -> validate.

	Normaliza el tax_id (sin guiones) y valida RNC / Cédula. Pasaporte se acepta tal cual.
	Empresas y proveedores de otro país conservan su ID fiscal sin validar (RFC, EIN, NIT...).
	"""
	if not doc.tax_id:
		return

	pais = doc.get("country")
	if pais and pais != "Dominican Republic":
		return

	# Clientes (no tienen país): un ID con letras es extranjero (pasaporte o ID tributaria)
	if not doc.meta.has_field("country") and re.search(r"[A-Za-z]", doc.tax_id):
		doc.tax_id = doc.tax_id.strip().upper()
		if doc.meta.has_field("rd_tipo_identificacion"):
			doc.rd_tipo_identificacion = "Pasaporte"
		return

	if doc.get("rd_tipo_identificacion") == "Pasaporte":
		doc.tax_id = doc.tax_id.strip().upper()
		return

	numero = limpiar_identificacion(doc.tax_id)
	tipo = doc.get("rd_tipo_identificacion") or tipo_identificacion(numero)
	if not tipo:
		frappe.throw(
			_("El RNC debe tener 9 dígitos y la Cédula 11 dígitos. Valor recibido: {0}").format(doc.tax_id),
			title=_("Identificación fiscal inválida"),
		)

	esperado = 9 if tipo == "RNC" else 11
	if len(numero) != esperado:
		frappe.throw(_("Un número de {0} debe tener {1} dígitos").format(tipo, esperado))

	if not identificacion_valida(numero, tipo):
		frappe.throw(
			_("El {0} {1} no es válido (dígito verificador incorrecto)").format(tipo, numero),
			title=_("Identificación fiscal inválida"),
		)

	doc.tax_id = numero
	if doc.meta.has_field("rd_tipo_identificacion"):
		doc.rd_tipo_identificacion = tipo
