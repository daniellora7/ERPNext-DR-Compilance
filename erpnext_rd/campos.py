"""Campos personalizados de la app en DocTypes de ERPNext y Frappe HR (instalación y migración).

Cada campo lleva el módulo de la app y solo se ve en empresas de RD (`rd_compliance/alcance.py`).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_rd.dgii_fiscal import isc
from erpnext_rd.dgii_fiscal.catalogos import (
	CONCEPTOS_FISCALES,
	DETALLES_SERVICIO_EXTERIOR,
	FORMAS_PAGO,
	TIPOS_ANULACION,
	TIPOS_BIENES_SERVICIOS,
	TIPOS_IDENTIFICACION,
	TIPOS_INGRESO,
	TIPOS_RETENCION_ISR,
	TIPOS_SERVICIO_EXTERIOR,
)
from erpnext_rd.dgii_fiscal.consulta_ncf import ESTADOS as ESTADOS_NCF_DGII
from erpnext_rd.dgii_fiscal.regimenes import REGIMENES as REGIMENES_ESPECIALES
from erpnext_rd.dgii_reportes import casillas_ir2
from erpnext_rd.dgii_reportes.ir2 import CATEGORIAS as CATEGORIAS_FISCALES
from erpnext_rd.nomina_rd import hrms_instalado
from erpnext_rd.nomina_rd.salario import CONCEPTOS as CONCEPTOS_NOMINA
from erpnext_rd.rd_compliance import alcance

MODULO = "DGII Fiscal"

# DocTypes de Frappe HR que reciben campos de la app (solo si hrms está instalado)
DOCTYPES_HRMS = (
	"Salary Component",
	"Gratuity Rule",
	"Gratuity",
	"Leave Type",
	"Leave Encashment",
	"Overtime Type",
)


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
	proporcionalidad = {
		"fieldname": "rd_itbis_proporcionalidad",
		"fieldtype": "Check",
		"label": "ITBIS sujeto a proporcionalidad (art. 349)",
		"description": "Gasto común a ventas gravadas y exentas (alquiler, teléfono, publicidad, asesorías): "
		"su ITBIS solo se adelanta en la proporción de las ventas gravadas del mes (IT-1, Anexo A).",
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
		{
			**proporcionalidad,
			"insert_after": "rd_detalle_servicio_exterior",
			"fetch_from": "supplier.rd_itbis_proporcionalidad",
			"allow_on_submit": 1,
			"depends_on": "eval:!['B17','E47'].includes(doc.rd_tipo_comprobante)",
		},
		{
			"fieldname": "rd_ncf_estado_dgii",
			"fieldtype": "Select",
			"label": "NCF en la DGII",
			"options": "\n" + "\n".join(ESTADOS_NCF_DGII),
			"insert_after": "rd_secuencia_ncf",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"print_hide": 1,
			"depends_on": "rd_ncf_estado_dgii",
			"description": "Resultado de la consulta de NCF de la DGII al guardar la factura",
		},
		{
			"fieldname": "rd_ncf_vigencia_dgii",
			"fieldtype": "Date",
			"label": "NCF válido hasta (DGII)",
			"insert_after": "rd_ncf_estado_dgii",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
			"print_hide": 1,
			"depends_on": "rd_ncf_vigencia_dgii",
		},
		# e-CF del proveedor (captura de compras) o el que emite la empresa (E41, E43, E47)
		{
			"fieldname": "rd_codigo_seguridad",
			"fieldtype": "Data",
			"label": "Código de seguridad e-CF",
			"insert_after": "rd_ncf_vigencia_dgii",
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

	return {
		"Company": [
			{
				"fieldname": "rd_perfil_tributario",
				"fieldtype": "Link",
				"label": "Perfil tributario",
				"options": "Perfil Tributario RD",
				"insert_after": "tax_id",
				"read_only": 1,
				"no_copy": 1,
				"description": "Se configura con el botón «Perfil tributario» (solo administradores)",
			},
			{
				"fieldname": "rd_catalogo_dgii",
				"fieldtype": "Check",
				"label": "Catálogo de cuentas DGII aplicado",
				"insert_after": "chart_of_accounts",
				"read_only": 1,
				"no_copy": 1,
				"description": "Lo marca ERPNext RD al crear el catálogo de cuentas conforme a la DGII",
			},
			{
				"fieldname": "rd_localidad_sirla",
				"fieldtype": "Data",
				"label": "Localidad SIRLA (RNL)",
				"insert_after": "rd_catalogo_dgii",
				"length": 6,
				"description": "Últimos 4 dígitos del Registro Nacional Laboral del establecimiento, para las planillas "
				"DGT-3 / DGT-4 del Ministerio de Trabajo. Un empleado de otro establecimiento lo indica en su ficha.",
			},
			{
				"fieldname": "rd_formato_factura",
				"fieldtype": "Link",
				"label": "Formato de impresión de facturas",
				"options": "Print Format",
				"insert_after": "rd_localidad_sirla",
				"link_filters": '[["Print Format","doc_type","=","Sales Invoice"],["Print Format","disabled","=",0]]',
				"description": "Formato con que se imprimen y envían por correo las facturas de venta de esta empresa. "
				"Vacío: Factura Fiscal RD en las empresas de República Dominicana y el formato estándar en las demás.",
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
			{
				"fieldname": "rd_casilla_ir2",
				"fieldtype": "Select",
				"label": "Casilla del IR-2 (anexos A-1 / B-1)",
				"options": _opciones(casillas_ir2.opciones()),
				"insert_after": "rd_tipo_ingreso",
				"description": "Vacío: la de la cuenta padre o, si ninguna la tiene, según el tipo de cuenta",
			},
		],
		"Customer": [
			tipo_identificacion,
			tipo_comprobante_defecto("rd_tipo_identificacion"),
			{
				"fieldname": "rd_regimen_especial",
				"fieldtype": "Select",
				"label": "Régimen especial",
				"options": _opciones(REGIMENES_ESPECIALES),
				"insert_after": "rd_tipo_comprobante",
				"description": "Zona franca u otro régimen especial: sus facturas salen con B14 / E44, sin ITBIS ni ISC "
				"(Norma General 05-2019). Las zonas francas comerciales no cambian el comprobante: la venta de "
				"mercancías se trata como exportación con la licencia de la DGA y el Formulario Único de Exportación.",
			},
			{
				"fieldname": "rd_carnet_regimen",
				"fieldtype": "Data",
				"label": "Carnet de Acreditación de Regímenes Especiales",
				"insert_after": "rd_regimen_especial",
				"depends_on": "eval:['Zona franca (Ley 8-90)', 'Otro régimen especial'].includes(doc.rd_regimen_especial)",
				"description": "Número del carnet, o de la resolución o contrato que avala la exención",
			},
			{
				"fieldname": "rd_carnet_vence",
				"fieldtype": "Date",
				"label": "Carnet vigente hasta",
				"insert_after": "rd_carnet_regimen",
				"depends_on": "eval:['Zona franca (Ley 8-90)', 'Otro régimen especial'].includes(doc.rd_regimen_especial)",
			},
			{
				"fieldname": "rd_licencia_dga",
				"fieldtype": "Data",
				"label": "Licencia de zona franca comercial (DGA)",
				"insert_after": "rd_carnet_vence",
				"depends_on": "eval:doc.rd_regimen_especial == 'Zona franca comercial'",
			},
			{
				"fieldname": "rd_unidad_compra_dgcp",
				"fieldtype": "Int",
				"label": "Unidad de compra (DGCP)",
				"insert_after": "rd_tipo_comprobante",
				"read_only": 1,
				"no_copy": 1,
				"depends_on": "rd_unidad_compra_dgcp",
				"description": "Institución del Estado creada desde un proceso de compra (Licitaciones del Estado)",
			},
		],
		"Opportunity": campos_oferta_estado(),
		"Sales Order": [
			{
				"fieldname": "rd_proceso_dgcp",
				"fieldtype": "Link",
				"label": "Proceso de compra del Estado",
				"options": "Proceso Compra DGCP",
				"insert_after": "po_date",
				"read_only": 1,
				"no_copy": 1,
				"depends_on": "rd_proceso_dgcp",
			},
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
			{
				**proporcionalidad,
				"label": "ITBIS sujeto a proporcionalidad por defecto (art. 349)",
				"insert_after": "rd_parte_relacionada",
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
		"Gratuity Rule": [
			{
				"fieldname": "rd_prestacion",
				"fieldtype": "Select",
				"label": "Prestación RD (Código de Trabajo)",
				"options": "\nCesantía\nPreaviso\nRegalía",
				"insert_after": "disable",
				"description": "Calcula el monto con los tramos de Configuración Nómina RD y el salario promedio "
				"del último año (regalía: salarios del año / 12), en vez de los tramos de esta regla.",
			},
		],
		"Gratuity": [
			{
				"fieldname": "rd_section_prestacion",
				"fieldtype": "Section Break",
				"label": "Cálculo de la prestación RD",
				"insert_after": "amount",
				"depends_on": "eval:doc.rd_meses_servicio",
			},
			{
				"fieldname": "rd_meses_servicio",
				"fieldtype": "Int",
				"label": "Meses de servicio",
				"read_only": 1,
				"insert_after": "rd_section_prestacion",
			},
			{
				"fieldname": "rd_dias",
				"fieldtype": "Float",
				"label": "Días de salario",
				"read_only": 1,
				"depends_on": "eval:doc.rd_dias",
				"insert_after": "rd_meses_servicio",
			},
			{
				"fieldname": "rd_column_prestacion",
				"fieldtype": "Column Break",
				"insert_after": "rd_dias",
			},
			{
				"fieldname": "rd_salario_promedio",
				"fieldtype": "Currency",
				"label": "Salario promedio mensual",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "rd_column_prestacion",
				"depends_on": "eval:doc.rd_dias",
			},
			{
				"fieldname": "rd_salario_diario",
				"fieldtype": "Currency",
				"label": "Salario diario",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "rd_salario_promedio",
				"depends_on": "eval:doc.rd_dias",
			},
			{
				"fieldname": "rd_salarios_del_anio",
				"fieldtype": "Currency",
				"label": "Salarios ordinarios del año",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "rd_salario_diario",
				"depends_on": "eval:doc.rd_salarios_del_anio",
				"description": "Regalía proporcional (art. 220): esta suma / 12",
			},
		],
		"Leave Type": [
			{
				"fieldname": "rd_vacaciones",
				"fieldtype": "Check",
				"label": "Vacaciones RD (Código de Trabajo)",
				"insert_after": "leave_type_name",
				"description": "Al terminar el contrato, el pago (Leave Encashment) suma la proporción del año "
				"incompleto (art. 180) y usa el salario diario de las prestaciones. Solo en empresas RD.",
			},
			{
				"fieldname": "rd_novedad_tss",
				"fieldtype": "Select",
				"label": "Novedad TSS",
				"options": "\nVC - Vacaciones\nLV - Licencia voluntaria\nLM - Licencia por maternidad\n"
				"LD - Licencia por discapacidad",
				"insert_after": "rd_vacaciones",
				"description": "Los permisos aprobados de este tipo van en el archivo de novedades de la TSS (NV) "
				"del mes en que empiezan.",
			},
		],
		"Overtime Type": [
			{
				"fieldname": "rd_horas_extras",
				"fieldtype": "Check",
				"label": "Horas extras RD (Código de Trabajo)",
				"insert_after": "overtime_salary_component",
				"description": "Valor de la hora con el salario ordinario / 23.83 / 8; recargo del 35 % hasta 68 horas "
				"semanales y del 100 % después, y del 100 % en feriados (Configuración Nómina RD). Solo en empresas RD.",
			},
		],
		"Leave Encashment": [
			{
				"fieldname": "rd_dias_proporcionales",
				"fieldtype": "Float",
				"label": "Días proporcionales (art. 180)",
				"read_only": 1,
				"insert_after": "leave_balance",
				"depends_on": "eval:doc.rd_salario_diario",
				"description": "Incluidos en el balance: proporción del año de servicio incompleto",
			},
			{
				"fieldname": "rd_salario_promedio",
				"fieldtype": "Currency",
				"label": "Salario promedio mensual",
				"options": "currency",
				"read_only": 1,
				"insert_after": "encashment_amount",
				"depends_on": "eval:doc.rd_salario_diario",
			},
			{
				"fieldname": "rd_salario_diario",
				"fieldtype": "Currency",
				"label": "Salario diario",
				"options": "currency",
				"read_only": 1,
				"insert_after": "rd_salario_promedio",
				"depends_on": "eval:doc.rd_salario_diario",
			},
		],
		"Employee": [
			{
				"fieldname": "rd_segundo_apellido",
				"fieldtype": "Data",
				"label": "Segundo apellido",
				"insert_after": "last_name",
				"description": "En el apellido va el primero. La TSS los pide por separado.",
			},
			{
				"fieldname": "rd_section_datos",
				"fieldtype": "Section Break",
				"label": "República Dominicana (TSS / DGII)",
				"insert_after": "date_of_joining",
				"description": "Datos para el archivo de la TSS (SUIR) y las declaraciones de la DGII (IR-3, IR-13). "
				"Solo se validan en empresas RD.",
			},
			{
				"fieldname": "rd_tipo_documento",
				"fieldtype": "Select",
				"label": "Tipo de documento",
				"options": "Cédula\nNSS\nPasaporte\nOtro",
				"default": "Cédula",
				"insert_after": "rd_section_datos",
				"description": "Extranjeros: pasaporte, carné de Migración u otro documento. Para cotizar, la TSS les "
				"asigna un NSS (SUIR → Solicitud de asignación de NSS); con NSS, el archivo de la TSS lo usa.",
			},
			{
				"fieldname": "rd_cedula",
				"fieldtype": "Data",
				"label": "Cédula",
				"insert_after": "rd_tipo_documento",
				"depends_on": "eval:doc.rd_tipo_documento == 'Cédula'",
				"search_index": 1,
				"in_standard_filter": 1,
				"description": "11 dígitos, con o sin guiones. Si no es válida, avisa pero deja guardar.",
			},
			{
				"fieldname": "rd_numero_documento",
				"fieldtype": "Data",
				"label": "Número del documento",
				"insert_after": "rd_cedula",
				"depends_on": "eval:['Pasaporte', 'Otro'].includes(doc.rd_tipo_documento)",
				"description": "El pasaporte también queda en Passport Number.",
			},
			{
				"fieldname": "rd_nss",
				"fieldtype": "Data",
				"label": "NSS (Seguridad Social)",
				"insert_after": "rd_numero_documento",
			},
			{
				"fieldname": "rd_column_datos",
				"fieldtype": "Column Break",
				"insert_after": "rd_nss",
			},
			{
				"fieldname": "rd_afp",
				"fieldtype": "Link",
				"label": "AFP",
				"options": "Entidad Seguridad Social RD",
				"insert_after": "rd_column_datos",
				"link_filters": '[["Entidad Seguridad Social RD","tipo","=","AFP"],'
				'["Entidad Seguridad Social RD","deshabilitada","=",0]]',
			},
			{
				"fieldname": "rd_ars",
				"fieldtype": "Link",
				"label": "ARS",
				"options": "Entidad Seguridad Social RD",
				"insert_after": "rd_afp",
				"link_filters": '[["Entidad Seguridad Social RD","tipo","=","ARS"],'
				'["Entidad Seguridad Social RD","deshabilitada","=",0]]',
			},
			{
				"fieldname": "rd_clave_nomina",
				"fieldtype": "Data",
				"label": "Clave de nómina TSS",
				"insert_after": "rd_ars",
				"length": 3,
				"default": "001",
				"description": "La nómina del SUIR donde está el trabajador (3 dígitos).",
			},
			{
				"fieldname": "rd_tipo_ingreso_tss",
				"fieldtype": "Select",
				"label": "Tipo de ingreso TSS",
				"insert_after": "rd_clave_nomina",
				"options": "\n0001 - Normal\n0002 - Trabajador ocasional (no fijo)\n0003 - Asalariado por hora o "
				"tiempo parcial\n0004 - No laboró mes completo\n0005 - Salario prorrateado semanal/bisemanal\n"
				"0006 - Pensionado antes de la Ley 87-01\n0007 - Exento por ley de pago al SDSS\n"
				"0008 - Trabajador con salario sectorizado",
				"description": "Vacío: Normal, o «No laboró mes completo» el mes en que entra o sale.",
			},
			{
				"fieldname": "rd_section_sirla",
				"fieldtype": "Section Break",
				"label": "Ministerio de Trabajo (SIRLA)",
				"insert_after": "rd_tipo_ingreso_tss",
				"collapsible": 1,
				"description": "Códigos de los catálogos del SIRLA para las planillas DGT-3 y DGT-4. El cargo es la "
				"designación del empleado.",
			},
			{
				"fieldname": "rd_ocupacion_sirla",
				"fieldtype": "Data",
				"label": "Código de ocupación",
				"insert_after": "rd_section_sirla",
				"length": 6,
			},
			{
				"fieldname": "rd_turno_sirla",
				"fieldtype": "Data",
				"label": "Código del turno",
				"insert_after": "rd_ocupacion_sirla",
				"length": 6,
				"description": "De la lista de turnos de la empresa en el SIRLA.",
			},
			{
				"fieldname": "rd_localidad_sirla",
				"fieldtype": "Data",
				"label": "Localidad (RNL)",
				"insert_after": "rd_turno_sirla",
				"length": 6,
				"description": "Vacío: la de la empresa.",
			},
			{
				"fieldname": "rd_column_sirla",
				"fieldtype": "Column Break",
				"insert_after": "rd_localidad_sirla",
			},
			{
				"fieldname": "rd_nivel_educativo_sirla",
				"fieldtype": "Data",
				"label": "Código de nivel educativo",
				"insert_after": "rd_column_sirla",
				"length": 5,
			},
			{
				"fieldname": "rd_discapacidad_sirla",
				"fieldtype": "Data",
				"label": "Códigos de discapacidad",
				"insert_after": "rd_nivel_educativo_sirla",
				"length": 50,
				"description": "Separados por comas, según el catálogo del SIRLA.",
			},
			{
				"fieldname": "rd_nacionalidad_sirla",
				"fieldtype": "Data",
				"label": "Código de nacionalidad",
				"insert_after": "rd_discapacidad_sirla",
				"length": 3,
				"description": "Solo para extranjeros.",
			},
			{
				"fieldname": "rd_section_dependientes",
				"fieldtype": "Section Break",
				"label": "Dependientes adicionales del SFS",
				"insert_after": "rd_nacionalidad_sirla",
				"collapsible": 1,
				"collapsible_depends_on": "rd_dependientes_adicionales",
				"description": "Padres, suegros e hijos mayores de 21 años que el trabajador afilió a su seguro de "
				"salud en la TSS. El per cápita de cada uno se descuenta en la nómina.",
			},
			{
				"fieldname": "rd_dependientes_adicionales",
				"fieldtype": "Table",
				"label": "Dependientes adicionales",
				"options": "Dependiente Adicional SFS",
				"insert_after": "rd_section_dependientes",
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
			*campos_isc_articulo(),
		],
		"Asset Category": [
			{
				"fieldname": "rd_categoria_fiscal",
				"fieldtype": "Select",
				"label": "Categoría fiscal (art. 287)",
				"options": _opciones(CATEGORIAS_FISCALES),
				"insert_after": "non_depreciable_category",
				"description": "1: edificaciones. 2: vehículos livianos, equipo y muebles de oficina, "
				"computadoras. 3: lo demás. Vacío: categoría 3 (o terreno si no se deprecia).",
			},
		],
		"Asset": [
			{
				"fieldname": "rd_dado_en_arrendamiento",
				"fieldtype": "Check",
				"label": "Dado en arrendamiento (art. 287, V)",
				"insert_after": "asset_category",
				"description": "Las categorías 2 y 3 dadas en arrendamiento se deprecian al 50% y 30% en el IR-2",
			},
		],
		"Sales Invoice": campos_venta("has_subcontracted"),
		"POS Invoice": campos_venta("return_against"),
		"Sales Invoice Item": campos_isc_linea(),
		"POS Invoice Item": campos_isc_linea(),
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


def campos_oferta_estado() -> list[dict]:
	"""Oportunidad de un proceso de compra del Estado (Fase 10.5, licitaciones/ofertas.py)."""
	en_oferta = "rd_proceso_dgcp"
	return [
		{
			"fieldname": "rd_proceso_dgcp",
			"fieldtype": "Link",
			"label": "Proceso de compra del Estado",
			"options": "Proceso Compra DGCP",
			"insert_after": "opportunity_type",
			"no_copy": 1,
			"search_index": 1,
		},
		{
			"fieldname": "rd_estado_oferta",
			"fieldtype": "Select",
			"label": "Estado de la oferta",
			"options": _opciones(
				(
					"Evaluando",
					"En preparación",
					"Presentada",
					"Ganada",
					"Perdida",
					"No presentada",
					"Desierto o cancelado",
				)
			),
			"insert_after": "rd_proceso_dgcp",
			"depends_on": en_oferta,
			"mandatory_depends_on": en_oferta,
			"in_standard_filter": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "rd_tab_licitacion",
			"fieldtype": "Tab Break",
			"label": "Licitación",
			"insert_after": "total",
			"depends_on": en_oferta,
		},
		{
			"fieldname": "rd_modalidad_dgcp",
			"fieldtype": "Data",
			"label": "Modalidad",
			"insert_after": "rd_tab_licitacion",
			"fetch_from": "rd_proceso_dgcp.modalidad",
			"read_only": 1,
		},
		{
			"fieldname": "rd_cierre_ofertas",
			"fieldtype": "Datetime",
			"label": "Recibe ofertas hasta",
			"insert_after": "rd_modalidad_dgcp",
			"read_only": 1,
			"no_copy": 1,
			"description": "Del proceso en la DGCP; se actualiza con cada descarga (enmiendas)",
		},
		{
			"fieldname": "rd_oferta_mipyme",
			"fieldtype": "Check",
			"label": "Oferta como MIPYME",
			"insert_after": "rd_cierre_ofertas",
			"description": "Del perfil de proveedor. Cambia las garantías: fiel cumplimiento menor, sin seriedad de la oferta y solo fianza",
		},
		{
			"fieldname": "rd_column_break_oferta",
			"fieldtype": "Column Break",
			"insert_after": "rd_oferta_mipyme",
		},
		{
			"fieldname": "rd_monto_oferta",
			"fieldtype": "Currency",
			"label": "Monto de la oferta",
			"options": "currency",
			"insert_after": "rd_column_break_oferta",
			"no_copy": 1,
			"description": "Vacío: el monto de la oportunidad. Sobre este monto se calculan las garantías",
		},
		{
			"fieldname": "rd_fecha_presentacion",
			"fieldtype": "Date",
			"label": "Presentada el",
			"insert_after": "rd_monto_oferta",
			"no_copy": 1,
		},
		{
			"fieldname": "rd_section_documentos",
			"fieldtype": "Section Break",
			"label": "Documentos de la oferta",
			"insert_after": "rd_fecha_presentacion",
		},
		{
			"fieldname": "rd_documentos_oferta",
			"fieldtype": "Table",
			"label": "Documentos",
			"options": "Documento Oferta Estado",
			"insert_after": "rd_section_documentos",
			"no_copy": 1,
		},
		{
			"fieldname": "rd_section_garantias",
			"fieldtype": "Section Break",
			"label": "Garantías",
			"insert_after": "rd_documentos_oferta",
			"description": "Porcentajes de Configuración de licitaciones. Confirme en el pliego: puede pedir otros",
		},
		{
			"fieldname": "rd_garantias",
			"fieldtype": "Table",
			"label": "Garantías",
			"options": "Garantia Oferta Estado",
			"insert_after": "rd_section_garantias",
			"no_copy": 1,
		},
	]


def campos_isc_articulo() -> list[dict]:
	"""Clasificación del ISC en el artículo (ver dgii_fiscal/isc.py). Cantidades por unidad de inventario."""
	es = "eval:doc.rd_isc_categoria == '{}'".format
	bien = "eval:{}.includes(doc.rd_isc_categoria)".format(list(isc.BIENES))
	return [
		{
			"fieldname": "rd_section_isc",
			"fieldtype": "Section Break",
			"label": "Impuesto selectivo al consumo (ISC)",
			"insert_after": "rd_bien_o_servicio",
			"collapsible": 1,
			"collapsible_depends_on": "rd_isc_categoria",
		},
		{
			"fieldname": "rd_isc_categoria",
			"fieldtype": "Select",
			"label": "Categoría del ISC",
			"options": _opciones(isc.CATEGORIAS),
			"insert_after": "rd_section_isc",
			"description": "Solo lo cobran las empresas que lo tienen en su perfil tributario",
		},
		{
			"fieldname": "rd_isc_producto",
			"fieldtype": "Select",
			"label": "Producto (e-CF)",
			"options": _opciones(isc.PRODUCTOS_ALCOHOL + isc.PRODUCTOS_TABACO),
			"insert_after": "rd_isc_categoria",
			"depends_on": "eval:['{}', '{}'].includes(doc.rd_isc_categoria)".format(isc.ALCOHOL, isc.TABACO),
			"description": "Tipo de bebida o de cigarrillo en la tabla de impuestos adicionales de la DGII: "
			"da el código del ISC en el e-CF",
		},
		{
			"fieldname": "rd_isc_origen",
			"fieldtype": "Select",
			"label": "Origen",
			"options": "\n".join((isc.PRODUCCION_LOCAL, isc.IMPORTADO)),
			"default": isc.PRODUCCION_LOCAL,
			"insert_after": "rd_isc_producto",
			"depends_on": bien,
			"description": "El ISC de los importados lo liquida la aduana: no se cobra al venderlos",
		},
		{
			"fieldname": "rd_isc_precio_por_menor",
			"fieldtype": "Currency",
			"label": "Precio de venta al por menor (ISC)",
			"options": "DOP",
			"insert_after": "rd_isc_origen",
			"depends_on": bien,
			"description": "Precio final al consumidor de una unidad de inventario, con envase, etiqueta y "
			"tapa (art. 367): base del ISC ad valorem",
		},
		{
			"fieldname": "rd_column_isc",
			"fieldtype": "Column Break",
			"insert_after": "rd_isc_precio_por_menor",
		},
		{
			"fieldname": "rd_isc_litros",
			"fieldtype": "Float",
			"label": "Litros por unidad",
			"insert_after": "rd_column_isc",
			"precision": "4",
			"depends_on": es(isc.ALCOHOL),
			"description": "Ej.: una caja de 24 botellas de 0.355 L = 8.52",
		},
		{
			"fieldname": "rd_isc_envases",
			"fieldtype": "Int",
			"label": "Envases por unidad",
			"insert_after": "rd_isc_litros",
			"default": "1",
			"depends_on": es(isc.ALCOHOL),
			"description": "Botellas o latas de una unidad de inventario (en el e-CF, la cantidad de "
			"referencia). Ej.: una caja de 24 botellas = 24",
		},
		{
			"fieldname": "rd_isc_grado",
			"fieldtype": "Percent",
			"label": "Grado alcohólico (% vol.)",
			"insert_after": "rd_isc_envases",
			"depends_on": es(isc.ALCOHOL),
		},
		{
			"fieldname": "rd_isc_cigarrillos",
			"fieldtype": "Select",
			"label": "Cigarrillos por cajetilla",
			"options": "\n20\n10",
			"insert_after": "rd_isc_grado",
			"depends_on": es(isc.TABACO),
		},
		{
			"fieldname": "rd_isc_cajetillas",
			"fieldtype": "Float",
			"label": "Cajetillas por unidad",
			"insert_after": "rd_isc_cigarrillos",
			"default": "1",
			"depends_on": es(isc.TABACO),
			"description": "Ej.: un cartón de 10 cajetillas = 10",
		},
		{
			"fieldname": "rd_isc_galones",
			"fieldtype": "Float",
			"label": "Galones por unidad",
			"insert_after": "rd_isc_cajetillas",
			"precision": "4",
			"depends_on": es(isc.COMBUSTIBLES),
		},
	]


def campos_isc_linea() -> list[dict]:
	"""ISC de cada línea de la factura de venta (lo calcula isc.aplicar). Montos en moneda de la empresa."""
	solo_lectura = {"read_only": 1, "no_copy": 1, "depends_on": "rd_isc_categoria"}
	return [
		{
			"fieldname": "rd_section_isc",
			"fieldtype": "Section Break",
			"label": "Impuesto selectivo al consumo (ISC)",
			"insert_after": "item_tax_rate",
			"collapsible": 1,
			"depends_on": "rd_isc_categoria",
		},
		{
			"fieldname": "rd_isc_categoria",
			"fieldtype": "Data",
			"label": "Categoría del ISC",
			"insert_after": "rd_section_isc",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "rd_isc_unitario",
			"fieldtype": "Float",
			"label": "ISC por unidad de inventario",
			"insert_after": "rd_isc_categoria",
			"precision": "6",
			"hidden": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "rd_isc_tasa",
			"fieldtype": "Percent",
			"label": "Tasa del ISC (servicios)",
			"insert_after": "rd_isc_unitario",
			**solo_lectura,
		},
		{
			"fieldname": "rd_isc_base_especifica",
			"fieldtype": "Float",
			"label": "Base del monto específico",
			"insert_after": "rd_isc_tasa",
			"precision": "4",
			**solo_lectura,
			"description": "Litros de alcohol absoluto, cajetillas o galones",
		},
		{
			"fieldname": "rd_column_isc",
			"fieldtype": "Column Break",
			"insert_after": "rd_isc_base_especifica",
		},
		{
			"fieldname": "rd_isc_base_ad_valorem",
			"fieldtype": "Currency",
			"label": "Base del ISC ad valorem",
			"options": "Company:company:default_currency",
			"insert_after": "rd_column_isc",
			**solo_lectura,
		},
		{
			"fieldname": "rd_isc_especifico",
			"fieldtype": "Currency",
			"label": "ISC específico",
			"options": "Company:company:default_currency",
			"insert_after": "rd_isc_base_ad_valorem",
			**solo_lectura,
		},
		{
			"fieldname": "rd_isc_ad_valorem",
			"fieldtype": "Currency",
			"label": "ISC ad valorem",
			"options": "Company:company:default_currency",
			"insert_after": "rd_isc_especifico",
			**solo_lectura,
		},
	]


def crear_campos_personalizados():
	campos = campos_personalizados()
	if not hrms_instalado():
		for doctype in DOCTYPES_HRMS:
			campos.pop(doctype, None)
	# DocTypes que solo traen las versiones recientes de Frappe HR (p. ej. Overtime Type)
	for doctype in [d for d in campos if not frappe.db.exists("DocType", d)]:
		campos.pop(doctype)
	for doctype, lista in campos.items():
		# Copias: varios DocTypes comparten la misma definición (p. ej. el tipo de identificación)
		campos[doctype] = [
			{
				**campo,
				"module": MODULO,
				# Solo se ven en empresas de RD (rd_compliance/alcance.py)
				"depends_on": alcance.condicion_campo(doctype, campo.get("depends_on")),
			}
			for campo in lista
		]
	create_custom_fields(campos, ignore_validate=True, update=True)
