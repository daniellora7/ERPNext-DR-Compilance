"""Instalación, migración y desinstalación: campos personalizados, catálogos DGII y menú.

Es idempotente: corre en after_install, after_migrate y cuando se instala Frappe HR. Todo se
configura solo, sin pasos en la consola, para que la app se pueda instalar desde Frappe Cloud.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_rd import formatos
from erpnext_rd.dgii_fiscal import catalogo_cuentas, cheque
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
from erpnext_rd.dgii_fiscal.consulta_ncf import ESTADOS as ESTADOS_NCF_DGII
from erpnext_rd.dgii_reportes import estados_ir2, ir2
from erpnext_rd.dgii_reportes.ir2 import CATEGORIAS as CATEGORIAS_FISCALES
from erpnext_rd.nomina_rd import hrms_instalado, salario, volante
from erpnext_rd.nomina_rd.salario import CONCEPTOS as CONCEPTOS_NOMINA

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
# Sidebar de la Nómina RD (nomina_rd/sidebar): vive en el dock de Frappe HR, no en RD Compliance
SIDEBAR_NOMINA = "Nomina RD"
FILA_DOCK_NOMINA = {"link_type": "Sidebar", "link_to": SIDEBAR_NOMINA}
# Ícono "soft" del dock (estilo de Frappe v16.52+); el de dos tonos queda para el encabezado del sidebar
ICONO_DOCK_NOMINA = "nomina-rd-soft"
ICONOS_DOCK_NOMINA_ANTERIORES = ("nomina-rd-duotone",)


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
				"depends_on": "eval:doc.country == 'Dominican Republic'",
				"description": "Lo marca ERPNext RD al crear el catálogo de cuentas conforme a la DGII",
			},
			{
				"fieldname": "rd_localidad_sirla",
				"fieldtype": "Data",
				"label": "Localidad SIRLA (RNL)",
				"insert_after": "rd_catalogo_dgii",
				"length": 6,
				"depends_on": "eval:doc.country == 'Dominican Republic'",
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
				"options": _opciones(estados_ir2.opciones()),
				"insert_after": "rd_tipo_ingreso",
				"description": "Vacío: la de la cuenta padre o, si ninguna la tiene, según el tipo de cuenta",
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
	# DocTypes que solo traen las versiones recientes de Frappe HR (p. ej. Overtime Type)
	for doctype in [d for d in campos if not frappe.db.exists("DocType", d)]:
		campos.pop(doctype)
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
	# Quedó vacío en los sitios donde la configuración se guardó antes de agregar el campo
	if not frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf"):
		frappe.db.set_single_value("Configuracion DGII", "ambiente_ecf", "TesteCF")
	for campo, valor in (
		("tasa_bcrd_activa", 1),
		("tasa_bcrd_tipo", "Compra"),
		("recordatorios_dias", 3),
		("consultar_ncf_dgii", 1),
		("anticipo_tasa_minima", 1.5),
		*ir2.TASAS_POR_DEFECTO.items(),
	):
		if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII", "field": campo}):
			frappe.db.set_single_value("Configuracion DGII", campo, valor)

	# Campos agregados después de guardar la configuración: quedan con su valor por defecto
	for campo, valor in (
		("calcular_deducciones", 1),
		("dias_salario_mes", 23.83),
		("actualizar_feriados", 1),
		("dia_descanso", "Sunday"),
		("bonificacion_porcentaje", 10),
		("bonificacion_anios", 3),
		("bonificacion_dias_menor", 45),
		("bonificacion_dias_mayor", 60),
		("horas_jornada", 8),
		("horas_semana_normal", 44),
		("horas_semana_maximo", 68),
		("recargo_horas_extras", 35),
		("recargo_horas_extras_exceso", 100),
		("recargo_feriado", 100),
		("recargo_nocturno", 15),
		("inicio_jornada_nocturna", "21:00:00"),
		("fin_jornada_nocturna", "07:00:00"),
		("sfs_per_capita_adicional", 1938.18),
		("fonamat_per_capita", 32.24),
		("subsidio_enfermedad_ambulatorio", 60),
		("subsidio_enfermedad_hospitalario", 40),
		("subsidio_dias_espera", 3),
		("subsidio_dias_maximo", 182),
		("subsidio_meses_promedio", 6),
		("subsidio_maternidad_meses", 3),
		("lactancia_un_salario", 33),
		("lactancia_dos_salarios", 12),
		("lactancia_tres_salarios", 6),
	):
		if not frappe.db.exists("Singles", {"doctype": "Configuracion Nomina RD", "field": campo}):
			frappe.db.set_single_value("Configuracion Nomina RD", campo, valor)

	dgii = frappe.get_single("Configuracion DGII")
	if not dgii.multiplicadores_inflacion:
		for cierre, valor, resolucion in ir2.MULTIPLICADORES:
			dgii.append(
				"multiplicadores_inflacion",
				{"cierre": cierre, "multiplicador": valor, "resolucion": resolucion},
			)
		dgii.save(ignore_permissions=True)

	conf = frappe.get_single("Configuracion Nomina RD")
	if not conf.escala_isr:
		from erpnext_rd.nomina_rd.calculos import ESCALAS_ISR

		for anio, escala in ESCALAS_ISR.items():
			agregar_escala_isr(conf, anio, escala)
		conf.save(ignore_permissions=True)


def agregar_escala_isr(conf, anio: int, escala):
	for desde, hasta, tasa, cuota in escala:
		conf.append(
			"escala_isr", {"anio": anio, "desde": desde, "hasta": hasta, "tasa": tasa, "cuota_fija": cuota}
		)


# Formatos que deja ERPNext al instalarse ("Classic" desde v16.5x; antes "Modern with Images"); se
# reemplazan por los fiscales. Si el usuario eligió otro formato, se respeta. Las empresas de otros
# países imprimen con el estándar o con el que indiquen (Company.rd_formato_factura, ver boot.py).
FORMATOS_POR_DEFECTO = {
	"Sales Invoice": ("Factura Fiscal RD", ("Sales Invoice Classic", "Sales Invoice Modern with Images")),
	"POS Invoice": ("Recibo POS RD (POS Invoice)", ("POS Invoice Classic", "POS Invoice Modern with Images")),
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
	"""Importa los sidebars de la app (RD Compliance y Nómina RD) si faltan.

	Al agregar un módulo a un sitio existente, su sidebar se sincroniza antes de que exista el
	Module Def y queda fuera hasta el siguiente migrate. Esto lo deja listo en la misma pasada.
	"""
	from frappe.modules.import_file import import_file_by_path

	for modulo, nombre in (("rd_compliance", "RD Compliance"), ("nomina_rd", SIDEBAR_NOMINA)):
		if frappe.db.exists("Sidebar", nombre):
			continue
		carpeta = frappe.scrub(nombre)
		import_file_by_path(
			frappe.get_app_path("erpnext_rd", modulo, "sidebar", carpeta, f"{carpeta}.json"), force=True
		)


def dock_nomina():
	"""Pone "Nómina RD" en el dock de Frappe HR si está instalado; si no, lo quita.

	Una app solo monta su dock sobre una app (el nuestro va en ERPNext con RD Compliance), así que la
	nómina entra por la capa del sitio del dock de Frappe HR, la misma que guarda "Organizar dock".
	No se toca el archivo de HRMS. Si el sitio no tenía arreglo propio, se crea con el orden de HRMS
	y la nómina al final; si ya lo tenía, solo se agrega la fila (y un usuario la puede ocultar).
	"""
	if not frappe.db.exists("DocType", "Dock"):
		return
	if not hrms_instalado():
		quitar_dock_nomina()
		return
	from frappe.desk.doctype.dock.dock import SITE_LAYER, get_app_base

	capas = _capas_dock_hrms()
	sitio = next((capa for capa in capas if not capa.user), None)
	if not sitio:
		sitio = frappe.new_doc("Dock")
		sitio.app, sitio.user = "hrms", SITE_LAYER
		for fila in get_app_base("hrms"):
			sitio.append("items", {**_destino(fila), "hidden": fila.get("hidden") or 0, "added": 0})
		capas.append(sitio)

	for capa in capas:
		existente = next((fila for fila in capa.items if _es_fila_nomina(fila)), None)
		if existente:
			# Sitios que ya tenían la entrada con el ícono anterior; uno elegido por el usuario se respeta
			if existente.icon in ICONOS_DOCK_NOMINA_ANTERIORES:
				existente.icon = ICONO_DOCK_NOMINA
				capa.save(ignore_permissions=True)
			continue
		# La capa del sitio trae la entrada (con ícono y título); la de un usuario solo la nombra,
		# porque una capa guardada es el dock completo y lo que no nombra no aparece.
		if capa is sitio:
			capa.append(
				"items", {**FILA_DOCK_NOMINA, "icon": ICONO_DOCK_NOMINA, "title": "Nómina RD", "added": 1}
			)
		else:
			capa.append("items", {**FILA_DOCK_NOMINA, "added": 0})
		capa.save(ignore_permissions=True)


def quitar_dock_nomina():
	"""Quita "Nómina RD" del dock de Frappe HR. Si la capa del sitio queda igual al dock de HRMS
	(la creó esta app y nadie la cambió), se borra para que el sitio vuelva al de HRMS."""
	if not frappe.db.exists("DocType", "Dock"):
		return
	from frappe.desk.doctype.dock.dock import get_app_dock

	base = (
		[(_destino(fila), fila.get("hidden") or 0) for fila in get_app_dock("hrms")]
		if hrms_instalado()
		else None
	)
	for capa in _capas_dock_hrms():
		filas = [fila for fila in capa.items if not _es_fila_nomina(fila)]
		if len(filas) == len(capa.items):
			continue
		sin_cambios = [
			(_destino(fila), fila.hidden or 0)
			for fila in filas
			if not (fila.added or fila.icon or fila.title)
		]
		if not capa.user and base is not None and len(sin_cambios) == len(filas) and sin_cambios == base:
			frappe.delete_doc("Dock", capa.name, force=True, ignore_permissions=True)
			continue
		capa.set("items", filas)
		capa.save(ignore_permissions=True)


def _capas_dock_hrms() -> list:
	"""Capas del dock de Frappe HR que no son el archivo de la app: la del sitio y las de usuarios."""
	return [
		frappe.get_doc("Dock", nombre)
		for nombre in frappe.get_all("Dock", filters={"app": "hrms", "standard": 0}, pluck="name")
	]


def _destino(fila) -> dict:
	return {campo: fila.get(campo) or None for campo in ("link_type", "link_to", "url")}


def _es_fila_nomina(fila) -> bool:
	return fila.get("link_type") == "Sidebar" and fila.get("link_to") == SIDEBAR_NOMINA


def prestaciones_y_feriados():
	"""Tramos de prestaciones y vacaciones en la configuración, reglas de Gratuity RD, el tipo de
	permiso Vacaciones RD y la lista de feriados RD."""
	from erpnext_rd.nomina_rd import feriados, prestaciones

	conf = frappe.get_single("Configuracion Nomina RD")
	if prestaciones.inicializar_tramos(conf):
		conf.save(ignore_permissions=True)
	if hrms_instalado():
		from erpnext_rd.nomina_rd import horas_extras, regalia, vacaciones

		reglas_gratuity_sin_tramos()
		periodo_opcional_en_vacaciones_rd()
		prestaciones.crear_reglas()
		vacaciones.crear_componente_y_tipo()
		regalia.crear_componente()
		horas_extras.crear_componente_y_tipo()
		volante.crear_formato()
	feriados.asegurar_lista_feriados()


def reglas_gratuity_sin_tramos():
	"""En una regla de prestación RD los tramos de HRMS (en años enteros) no aplican: se ocultan y
	dejan de ser obligatorios, igual que los componentes. En las demás reglas siguen igual."""
	ajustes = (
		("gratuity_rule_slabs", "reqd", "0", "Check"),
		("gratuity_rule_slabs", "mandatory_depends_on", "eval:!doc.rd_prestacion", "Code"),
		("gratuity_rule_slabs", "depends_on", "eval:!doc.rd_prestacion", "Code"),
		# Componentes opcionales: vacío = los ingresos que cotizan a la TSS (prestaciones.componentes_ordinarios)
		("applicable_earnings_component", "reqd", "0", "Check"),
		("applicable_earnings_component", "mandatory_depends_on", "eval:!doc.rd_prestacion", "Code"),
	)
	_property_setters("Gratuity Rule", ajustes)


def datos_del_empleado():
	"""Catálogo de AFP y ARS, y buscar empleados también por cédula."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	from erpnext_rd.nomina_rd import empleado

	empleado.crear_entidades()
	campos = [c.strip() for c in (frappe.get_meta("Employee").search_fields or "").split(",") if c.strip()]
	if "rd_cedula" not in campos:
		make_property_setter(
			"Employee",
			None,
			"search_fields",
			", ".join([*campos, "rd_cedula"]),
			"Data",
			for_doctype=True,
			validate_fields_for_doctype=False,
		)
		frappe.db.set_value(
			"Property Setter",
			{"doc_type": "Employee", "property": "search_fields", "module": ("is", "not set")},
			"module",
			MODULO,
			update_modified=False,
		)


def periodo_opcional_en_vacaciones_rd():
	"""El *Leave Period* del Leave Encashment lo pone la app en el pago de vacaciones RD (ver
	`leave_encashment_rd`); en los demás pagos sigue siendo obligatorio como en Frappe HR."""
	_property_setters(
		"Leave Encashment",
		(
			("leave_period", "reqd", "0", "Check"),
			("leave_period", "mandatory_depends_on", "eval:!doc.rd_salario_diario", "Code"),
		),
	)


def _property_setters(doctype: str, ajustes):
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for campo, propiedad, valor, tipo in ajustes:
		make_property_setter(doctype, campo, propiedad, valor, tipo, validate_fields_for_doctype=False)
	# Con el módulo de la app, Frappe los borra al desinstalarla
	frappe.db.set_value(
		"Property Setter",
		{
			"doc_type": doctype,
			"module": ("is", "not set"),
			"field_name": ("in", {a[0] for a in ajustes}),
		},
		"module",
		MODULO,
		update_modified=False,
	)


def programar_padron_inicial():
	"""Sitio nuevo: descarga el padrón RNC en segundo plano (cola long), sin pasos en la consola.

	Después lo actualiza la tarea diaria (solo si la DGII publicó uno nuevo) o el botón de Configuración DGII."""
	if frappe.flags.in_test or getattr(frappe, "in_test", False):
		return
	if frappe.get_all("Contribuyente DGII", limit=1):
		return
	from erpnext_rd.padron_rnc.padron import encolar

	encolar()


def lista_padron_sin_filtro_reciente():
	"""El padrón (~800 mil filas) es una tabla grande para Frappe, que entonces filtra la lista por
	"creados en los últimos 90 días" y avisa cada vez. En el padrón se busca por RNC o nombre, no por
	fecha: se desactiva ese filtro. Solo si no existe la configuración, para respetar la del usuario."""
	if frappe.db.exists("List View Settings", "Contribuyente DGII"):
		return
	frappe.get_doc(
		{
			"doctype": "List View Settings",
			"name": "Contribuyente DGII",
			"disable_automatic_recency_filters": 1,
		}
	).insert(ignore_permissions=True)


def setup():
	crear_campos_personalizados()
	formatos.asegurar_fiscales()
	cheque.crear_formato()
	ir2.crear_formato()
	estados_ir2.asignar_casillas()
	formato_impresion_por_defecto()
	crear_tipos_comprobante()
	inicializar_formas_pago()
	inicializar_configuracion()
	asegurar_navegacion()
	dock_nomina()
	datos_del_empleado()
	prestaciones_y_feriados()
	lista_padron_sin_filtro_reciente()
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
	"""after_app_uninstall: sin Frappe HR se quitan sus campos y la Nómina RD del dock."""
	if app_name != "hrms":
		return
	for nombre in frappe.get_all(
		"Custom Field", filters={"dt": ("in", DOCTYPES_HRMS), "module": MODULO}, pluck="name"
	):
		frappe.delete_doc("Custom Field", nombre, force=True, ignore_permissions=True)
	frappe.db.delete("Property Setter", {"doc_type": ("in", DOCTYPES_HRMS), "module": MODULO})
	quitar_dock_nomina()
	volante.quitar_formato()
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
	volante.quitar_formato()
	for job in frappe.get_all(
		"Scheduled Job Type", filters={"method": ("like", "erpnext_rd.%")}, pluck="name"
	):
		frappe.delete_doc("Scheduled Job Type", job, force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", "Dock") and frappe.db.exists("Dock", "erpnext_rd"):
		frappe.delete_doc("Dock", "erpnext_rd", force=True, ignore_permissions=True)
	quitar_dock_nomina()
	frappe.db.delete("List View Settings", {"name": "Contribuyente DGII"})
	frappe.db.delete("DefaultValue", {"defkey": ("like", "erpnext_rd_%")})
	frappe.clear_cache()
