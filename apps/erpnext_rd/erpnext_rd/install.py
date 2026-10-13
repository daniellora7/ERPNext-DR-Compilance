"""Instalación y migración: campos personalizados y catálogos DGII.

Es idempotente: corre en after_install y after_migrate.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_rd.dgii_fiscal.catalogos import (
	TIPOS_ANULACION,
	TIPOS_BIENES_SERVICIOS,
	TIPOS_COMPROBANTE,
	TIPOS_IDENTIFICACION,
	TIPOS_INGRESO,
)

MODULO = "DGII Fiscal"


def _opciones(lista):
	return "\n" + "\n".join(lista)


def campos_personalizados() -> dict:
	tipo_identificacion = {
		"fieldname": "rd_tipo_identificacion",
		"fieldtype": "Select",
		"label": "Tipo de identificación",
		"options": _opciones(TIPOS_IDENTIFICACION),
		"insert_after": "tax_id",
		"description": "Se detecta automáticamente por la cantidad de dígitos (9 = RNC, 11 = Cédula)",
	}

	def tipo_comprobante_defecto(insert_after):
		return {
			"fieldname": "rd_tipo_comprobante",
			"fieldtype": "Link",
			"label": "Tipo de comprobante por defecto",
			"options": "Tipo Comprobante Fiscal",
			"insert_after": insert_after,
		}

	bienes_servicios = {
		"fieldname": "rd_tipo_bienes_servicios",
		"fieldtype": "Select",
		"label": "Tipo de bienes y servicios (606)",
		"options": _opciones(TIPOS_BIENES_SERVICIOS),
	}

	def seccion_factura(insert_after):
		return [
			{
				"fieldname": "rd_section_dgii",
				"fieldtype": "Section Break",
				"label": "Comprobante fiscal (DGII)",
				"insert_after": insert_after,
			},
			{
				"fieldname": "rd_tipo_comprobante",
				"fieldtype": "Link",
				"label": "Tipo de comprobante",
				"options": "Tipo Comprobante Fiscal",
				"insert_after": "rd_section_dgii",
				"in_standard_filter": 1,
				"allow_on_submit": 0,
			},
			{
				"fieldname": "rd_ncf",
				"fieldtype": "Data",
				"label": "NCF",
				"insert_after": "rd_tipo_comprobante",
				"no_copy": 1,
				"in_standard_filter": 1,
				"search_index": 1,
				"length": 13,
			},
			{
				"fieldname": "rd_ncf_vencimiento",
				"fieldtype": "Date",
				"label": "Vencimiento del NCF",
				"insert_after": "rd_ncf",
				"no_copy": 1,
				"read_only": 1,
			},
			{
				"fieldname": "rd_secuencia_ncf",
				"fieldtype": "Link",
				"label": "Secuencia NCF",
				"options": "Secuencia NCF",
				"insert_after": "rd_ncf_vencimiento",
				"no_copy": 1,
				"read_only": 1,
				"print_hide": 1,
			},
			{
				"fieldname": "rd_column_break_dgii",
				"fieldtype": "Column Break",
				"insert_after": "rd_secuencia_ncf",
			},
			{
				"fieldname": "rd_ncf_modificado",
				"fieldtype": "Data",
				"label": "NCF modificado",
				"insert_after": "rd_column_break_dgii",
				"no_copy": 1,
				"length": 13,
				"depends_on": "eval:doc.is_return || doc.is_debit_note",
				"description": "NCF de la factura original que afecta esta nota de crédito / débito",
			},
		]

	venta = seccion_factura("has_subcontracted")
	venta[2]["read_only"] = 1  # en ventas el NCF siempre lo asigna el sistema
	venta += [
		{
			"fieldname": "rd_tipo_ingreso",
			"fieldtype": "Select",
			"label": "Tipo de ingreso (607)",
			"options": _opciones(TIPOS_INGRESO),
			"insert_after": "rd_ncf_modificado",
		},
		{
			"fieldname": "rd_tipo_anulacion",
			"fieldtype": "Select",
			"label": "Tipo de anulación (608)",
			"options": _opciones(TIPOS_ANULACION),
			"insert_after": "rd_tipo_ingreso",
			"allow_on_submit": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.docstatus > 0 && doc.rd_ncf",
			"description": "Requerido para cancelar una factura con NCF",
		},
	]

	compra = seccion_factura("bill_date")
	compra[2]["description"] = (
		"NCF del comprobante del proveedor. En B11 / B13 / B17 (E41 / E43 / E47) lo asigna el sistema."
	)
	compra += [
		{**bienes_servicios, "insert_after": "rd_ncf_modificado"},
	]

	return {
		"Customer": [
			tipo_identificacion,
			tipo_comprobante_defecto("rd_tipo_identificacion"),
		],
		"Supplier": [
			tipo_identificacion,
			tipo_comprobante_defecto("rd_tipo_identificacion"),
			{**bienes_servicios, "insert_after": "rd_tipo_comprobante", "label": "Tipo de bienes y servicios por defecto (606)"},
		],
		"Sales Invoice": venta,
		"Purchase Invoice": compra,
	}


def crear_campos_personalizados():
	campos = campos_personalizados()
	for lista in campos.values():
		for campo in lista:
			campo["module"] = MODULO
	create_custom_fields(campos, ignore_validate=True, update=True)


def crear_tipos_comprobante():
	"""Inserta los tipos faltantes. No sobrescribe cambios que el usuario haya hecho."""
	for codigo, descripcion, ventas, compras, comprador, nota, requiere_rnc in TIPOS_COMPROBANTE:
		if frappe.db.exists("Tipo Comprobante Fiscal", codigo):
			continue
		frappe.get_doc(
			{
				"doctype": "Tipo Comprobante Fiscal",
				"codigo": codigo,
				"descripcion": descripcion,
				"serie": codigo[0],
				"habilitado": 1,
				"aplica_ventas": ventas,
				"aplica_compras": compras,
				"emitido_por_comprador": comprador,
				"nota": nota,
				"requiere_rnc": requiere_rnc,
			}
		).insert(ignore_permissions=True)


def inicializar_configuracion():
	"""Guarda la Configuracion DGII una vez para que sus valores por defecto queden en la base."""
	if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII"}):
		frappe.get_single("Configuracion DGII").save(ignore_permissions=True)


def setup():
	crear_campos_personalizados()
	crear_tipos_comprobante()
	inicializar_configuracion()
	frappe.clear_cache()


def after_install():
	setup()


def after_migrate():
	setup()
