"""Instalación, migración y desinstalación: campos personalizados, catálogos DGII y menú.

Es idempotente: corre en after_install, after_migrate y cuando se instala Frappe HR. Todo se
configura solo, sin pasos en la consola, para que la app se pueda instalar desde Frappe Cloud.
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
from erpnext_rd.nomina_rd import hrms_instalado, salario
from erpnext_rd.nomina_rd.salario import CONCEPTOS as CONCEPTOS_NOMINA

MODULO = "DGII Fiscal"

# DocTypes de Frappe HR que reciben campos de la app (solo si hrms está instalado)
DOCTYPES_HRMS = ("Salary Component",)
SIDEBAR = "RD Compliance"
SECCION_NOMINA = "Nómina RD"


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
			{
				**bienes_servicios,
				"insert_after": "rd_tipo_comprobante",
				"label": "Tipo de bienes y servicios por defecto (606)",
			},
			{
				"fieldname": "rd_parte_relacionada",
				"fieldtype": "Check",
				"label": "Parte relacionada (609)",
				"insert_after": "rd_tipo_bienes_servicios",
				"description": "Art. 281 del Código Tributario. Solo aplica a proveedores del exterior.",
			},
		],
		"Salary Component": [
			{
				"fieldname": "rd_concepto_nomina",
				"fieldtype": "Select",
				"label": "Cálculo de ley RD",
				"options": _opciones(CONCEPTOS_NOMINA),
				"insert_after": "type",
				"description": "Si se indica, ERPNext RD calcula el monto (TSS / ISR) según la Configuración Nómina RD",
			},
			{
				"fieldname": "rd_cotiza_tss",
				"fieldtype": "Check",
				"label": "Cotiza a la TSS",
				"default": "1",
				"insert_after": "rd_concepto_nomina",
				"depends_on": "eval:doc.type == 'Earning'",
				"description": "Suma al salario cotizable de AFP, SFS y SRL. Desmarcar para regalía pascual, "
				"bonificaciones y otros ingresos no cotizables.",
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
	if not hrms_instalado():
		for doctype in DOCTYPES_HRMS:
			campos.pop(doctype, None)
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
	"""Guarda las configuraciones una vez para que sus valores por defecto queden en la base."""
	if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII"}):
		frappe.get_single("Configuracion DGII").save(ignore_permissions=True)

	# Campos Check agregados después de guardar la configuración: quedan con su valor por defecto
	for campo in ("calcular_deducciones",):
		if not frappe.db.exists("Singles", {"doctype": "Configuracion Nomina RD", "field": campo}):
			frappe.db.set_single_value("Configuracion Nomina RD", campo, 1)

	conf = frappe.get_single("Configuracion Nomina RD")
	if not conf.escala_isr:
		from erpnext_rd.nomina_rd.calculos import ESCALA_ISR_2026

		for desde, hasta, tasa, cuota in ESCALA_ISR_2026:
			conf.append("escala_isr", {"desde": desde, "hasta": hasta, "tasa": tasa, "cuota_fija": cuota})
		conf.save(ignore_permissions=True)


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
				doctype,
				None,
				"default_print_format",
				formato,
				"Data",
				for_doctype=True,
				validate_fields_for_doctype=False,
			)

	# Con el módulo puesto, Frappe los borra al desinstalar la app junto con los formatos
	frappe.db.set_value(
		"Property Setter",
		{
			"property": "default_print_format",
			"value": ("in", _formatos_fiscales()),
			"module": ("is", "not set"),
		},
		"module",
		MODULO,
		update_modified=False,
	)


def _formatos_fiscales() -> list[str]:
	return [formato for formato, _reemplazables in FORMATOS_POR_DEFECTO.values()]


def asegurar_navegacion():
	"""Importa el sidebar de RD Compliance si falta.

	Al agregar el módulo a un sitio existente, el sidebar se sincroniza antes de que exista el
	Module Def y queda fuera hasta el siguiente migrate. Esto lo deja listo en la misma pasada.
	"""
	if frappe.db.exists("Sidebar", "RD Compliance"):
		return
	from frappe.modules.import_file import import_file_by_path

	ruta = frappe.get_app_path(
		"erpnext_rd", "rd_compliance", "sidebar", "rd_compliance", "rd_compliance.json"
	)
	import_file_by_path(ruta, force=True)


def ajustar_menu_nomina():
	"""Muestra la sección Nómina RD del menú solo si Frappe HR está instalado."""
	if not frappe.db.exists("Sidebar", SIDEBAR):
		return
	oculto = 0 if hrms_instalado() else 1
	en_nomina = False
	for fila in frappe.get_all(
		"Sidebar Item",
		filters={"parent": SIDEBAR, "parenttype": "Sidebar"},
		fields=["name", "type", "label", "hidden"],
		order_by="idx",
	):
		if fila.type == "Section Break":
			en_nomina = fila.label == SECCION_NOMINA
		if en_nomina and fila.hidden != oculto:
			frappe.db.set_value("Sidebar Item", fila.name, "hidden", oculto, update_modified=False)


def programar_padron_inicial():
	"""Sitio nuevo: descarga el padrón RNC en segundo plano (cola long), sin pasos en la consola.

	Después lo actualiza la tarea semanal o el botón de Configuración DGII."""
	if frappe.flags.in_test or getattr(frappe, "in_test", False):
		return
	if frappe.get_all("Contribuyente DGII", limit=1):
		return
	from erpnext_rd.padron_rnc.padron import encolar

	encolar()


def setup():
	crear_campos_personalizados()
	formato_impresion_por_defecto()
	crear_tipos_comprobante()
	inicializar_formas_pago()
	inicializar_configuracion()
	asegurar_navegacion()
	ajustar_menu_nomina()
	frappe.clear_cache()
	catalogo_cuentas.aplicar_a_empresas_rd()
	salario.crear_componentes()


def after_install():
	setup()
	programar_padron_inicial()


def after_migrate():
	setup()
	programar_padron_inicial()


def al_instalar_app(app_name: str):
	"""after_app_install: Frappe HR instalado después de esta app -> activa la Nómina RD."""
	if app_name == "hrms":
		setup()


def al_desinstalar_app(app_name: str):
	"""after_app_uninstall: sin Frappe HR se quitan sus campos y la sección del menú."""
	if app_name != "hrms":
		return
	for nombre in frappe.get_all(
		"Custom Field", filters={"dt": ("in", DOCTYPES_HRMS), "module": MODULO}, pluck="name"
	):
		frappe.delete_doc("Custom Field", nombre, force=True, ignore_permissions=True)
	ajustar_menu_nomina()
	# Frappe llama este hook después del último commit de la desinstalación
	frappe.db.commit()  # nosemgrep
	frappe.clear_cache()


def before_uninstall():
	"""Quita lo que Frappe no borra solo al desinstalar (lo que no cuelga de un módulo de la app).

	Campos personalizados, formatos, reportes, DocTypes y el menú tienen módulo y los borra Frappe.
	Los datos contables del usuario (cuentas, plantillas de impuestos, facturas) se conservan."""
	frappe.db.delete(
		"Property Setter", {"property": "default_print_format", "value": ("in", _formatos_fiscales())}
	)
	for job in frappe.get_all(
		"Scheduled Job Type", filters={"method": ("like", "erpnext_rd.%")}, pluck="name"
	):
		frappe.delete_doc("Scheduled Job Type", job, force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", "Dock") and frappe.db.exists("Dock", "erpnext_rd"):
		frappe.delete_doc("Dock", "erpnext_rd", force=True, ignore_permissions=True)
	frappe.clear_cache()
