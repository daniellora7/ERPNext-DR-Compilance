"""Instalación y migración: campos personalizados y catálogos DGII.

Es idempotente: corre en after_install y after_migrate.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_rd.dgii_fiscal import catalogo_cuentas
from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.catalogos import (
	CONCEPTOS_FISCALES,
	DETALLES_SERVICIO_EXTERIOR,
	FORMAS_PAGO,
	TIPOS_ANULACION,
	TIPOS_BIENES_SERVICIOS,
	TIPOS_COMPROBANTE,
	TIPOS_IDENTIFICACION,
	TIPOS_INGRESO,
	TIPOS_RETENCION_ISR,
	TIPOS_SERVICIO_EXTERIOR,
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

	def fecha_anulacion(insert_after):
		return {
			"fieldname": "rd_fecha_anulacion",
			"fieldtype": "Date",
			"label": "Fecha de anulación (608)",
			"insert_after": insert_after,
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"depends_on": "eval:doc.docstatus == 2 && doc.rd_ncf",
		}

	def campos_venta(insert_after):
		campos = seccion_factura(insert_after)
		campos[2]["read_only"] = 1  # en ventas el NCF siempre lo asigna el sistema
		campos += [
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
			fecha_anulacion("rd_tipo_anulacion"),
			# e-CF: los llena la firma electrónica (Fase 4); el QR se imprime cuando existen
			{
				"fieldname": "rd_codigo_seguridad",
				"fieldtype": "Data",
				"label": "Código de seguridad e-CF",
				"insert_after": "rd_fecha_anulacion",
				"read_only": 1,
				"no_copy": 1,
				"length": 6,
				"depends_on": "eval:(doc.rd_ncf || '').startsWith('E')",
			},
			{
				"fieldname": "rd_fecha_firma",
				"fieldtype": "Datetime",
				"label": "Fecha de firma e-CF",
				"insert_after": "rd_codigo_seguridad",
				"read_only": 1,
				"no_copy": 1,
				"depends_on": "eval:(doc.rd_ncf || '').startsWith('E')",
			},
		]
		return campos

	compra = seccion_factura("bill_date")
	compra[2]["description"] = (
		"NCF del comprobante del proveedor. En B11 / B13 / B17 (E41 / E43 / E47) lo asigna el sistema."
	)
	compra += [
		{**bienes_servicios, "insert_after": "rd_ncf_modificado"},
		{
			"fieldname": "rd_tipo_retencion_isr",
			"fieldtype": "Select",
			"label": "Tipo de retención ISR (606)",
			"options": _opciones(TIPOS_RETENCION_ISR),
			"insert_after": "rd_tipo_bienes_servicios",
			"allow_on_submit": 1,
			"description": "Requerido cuando se retiene ISR al proveedor",
		},
		{
			"fieldname": "rd_tipo_anulacion",
			"fieldtype": "Select",
			"label": "Tipo de anulación (608)",
			"options": _opciones(TIPOS_ANULACION),
			"insert_after": "rd_tipo_retencion_isr",
			"allow_on_submit": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.docstatus > 0 && doc.rd_ncf && "
			"['B11','B13','B17','E41','E43','E47'].includes(doc.rd_tipo_comprobante)",
			"description": "Requerido para cancelar un comprobante emitido por la empresa (B11, B13, B17)",
		},
		fecha_anulacion("rd_tipo_anulacion"),
		{
			"fieldname": "rd_tipo_servicio_exterior",
			"fieldtype": "Select",
			"label": "Tipo de servicio del exterior (609)",
			"options": _opciones(TIPOS_SERVICIO_EXTERIOR),
			"insert_after": "rd_fecha_anulacion",
			"allow_on_submit": 1,
			"depends_on": "eval:['B17','E47'].includes(doc.rd_tipo_comprobante)",
		},
		{
			"fieldname": "rd_detalle_servicio_exterior",
			"fieldtype": "Select",
			"label": "Detalle del servicio del exterior (609)",
			"options": _opciones(DETALLES_SERVICIO_EXTERIOR),
			"insert_after": "rd_tipo_servicio_exterior",
			"allow_on_submit": 1,
			"depends_on": "eval:['B17','E47'].includes(doc.rd_tipo_comprobante)",
		},
	]

	return {
		"Company": [
			{
				"fieldname": "rd_catalogo_dgii",
				"fieldtype": "Check",
				"label": "Catálogo de cuentas DGII aplicado",
				"insert_after": "chart_of_accounts",
				"read_only": 1,
				"no_copy": 1,
				"depends_on": "eval:doc.country == 'Dominican Republic'",
				"description": "Lo marca ERPNext RD al crear el catálogo de cuentas conforme a la DGII",
			},
		],
		"Account": [
			{
				"fieldname": "rd_concepto_fiscal",
				"fieldtype": "Select",
				"label": "Concepto fiscal DGII",
				"options": _opciones(CONCEPTOS_FISCALES),
				"insert_after": "account_type",
				"description": "Columna del 606 / 607 donde se reporta el impuesto registrado en esta cuenta",
			},
			{
				**bienes_servicios,
				"insert_after": "rd_concepto_fiscal",
				"depends_on": "eval:doc.root_type == 'Expense'",
				"description": "Se sugiere en las facturas de compra que usan esta cuenta de gasto",
			},
			{
				"fieldname": "rd_tipo_ingreso",
				"fieldtype": "Select",
				"label": "Tipo de ingreso (607)",
				"options": _opciones(TIPOS_INGRESO),
				"insert_after": "rd_tipo_bienes_servicios",
				"depends_on": "eval:doc.root_type == 'Income'",
				"description": "Se sugiere en las facturas de venta que usan esta cuenta de ingreso",
			},
		],
		"Customer": [
			tipo_identificacion,
			tipo_comprobante_defecto("rd_tipo_identificacion"),
		],
		"Supplier": [
			tipo_identificacion,
			tipo_comprobante_defecto("rd_tipo_identificacion"),
			{**bienes_servicios, "insert_after": "rd_tipo_comprobante", "label": "Tipo de bienes y servicios por defecto (606)"},
			{
				"fieldname": "rd_parte_relacionada",
				"fieldtype": "Check",
				"label": "Parte relacionada (609)",
				"insert_after": "rd_tipo_bienes_servicios",
				"description": "Art. 281 del Código Tributario. Solo aplica a proveedores del exterior.",
			},
		],
		"Mode of Payment": [
			{
				"fieldname": "rd_forma_pago",
				"fieldtype": "Select",
				"label": "Forma de pago DGII (606 / 607)",
				"options": _opciones(FORMAS_PAGO),
				"insert_after": "type",
			},
		],
		"Item": [
			{
				"fieldname": "rd_bien_o_servicio",
				"fieldtype": "Select",
				"label": "Bien o servicio (606)",
				"options": "\nBien\nServicio",
				"insert_after": "is_stock_item",
				"description": "Vacío = automático: los artículos de inventario y los activos fijos son bienes",
			},
		],
		"Sales Invoice": campos_venta("has_subcontracted"),
		"POS Invoice": campos_venta("return_against"),
		"POS Profile": [
			{
				"fieldname": "rd_tipo_comprobante",
				"fieldtype": "Link",
				"label": "Tipo de comprobante por defecto",
				"options": "Tipo Comprobante Fiscal",
				"insert_after": "customer",
				"description": "Para clientes sin RNC ni tipo propio (normalmente B02 / E32 consumo)",
			},
		],
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


def inicializar_formas_pago():
	"""Clasifica los Modos de Pago existentes que aún no tienen forma de pago DGII."""
	for modo in frappe.get_all(
		"Mode of Payment", filters={"rd_forma_pago": ("is", "not set")}, fields=["name", "type"]
	):
		nombre = modo.name.lower()
		if "card" in nombre or "tarjeta" in nombre:
			forma = cat.TARJETA
		elif modo.type == "Cash":
			forma = cat.EFECTIVO
		elif modo.type == "Bank":
			forma = cat.CHEQUE_TRANSFERENCIA
		else:
			forma = cat.OTRAS_FORMAS
		frappe.db.set_value("Mode of Payment", modo.name, "rd_forma_pago", forma, update_modified=False)


def inicializar_configuracion():
	"""Guarda la Configuracion DGII una vez para que sus valores por defecto queden en la base."""
	if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII"}):
		frappe.get_single("Configuracion DGII").save(ignore_permissions=True)


# Formatos que deja el asistente de configuración de ERPNext; se reemplazan por los fiscales.
# Si el usuario eligió otro formato, se respeta.
FORMATOS_POR_DEFECTO = {
	"Sales Invoice": ("Factura Fiscal RD", ("Sales Invoice Modern with Images",)),
	"POS Invoice": ("Recibo POS RD (POS Invoice)", ("POS Invoice Modern with Images",)),
}


def formato_impresion_por_defecto():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, (formato, reemplazables) in FORMATOS_POR_DEFECTO.items():
		actual = frappe.db.get_value(
			"Property Setter", {"doc_type": doctype, "property": "default_print_format"}, "value"
		)
		if not actual or actual in reemplazables:
			make_property_setter(
				doctype, None, "default_print_format", formato, "Data", for_doctype=True,
				validate_fields_for_doctype=False,
			)


def setup():
	crear_campos_personalizados()
	formato_impresion_por_defecto()
	crear_tipos_comprobante()
	inicializar_formas_pago()
	inicializar_configuracion()
	frappe.clear_cache()
	catalogo_cuentas.aplicar_a_empresas_rd()


def after_install():
	setup()


def after_migrate():
	setup()
