"""Catálogos de la DGII usados en comprobantes y en los formatos 606/607/608."""

# codigo, descripcion, aplica_ventas, aplica_compras, emitido_por_comprador, nota, requiere_rnc
TIPOS_COMPROBANTE = [
	("B01", "Factura de Crédito Fiscal", 1, 1, 0, "", 1),
	("B02", "Factura de Consumo", 1, 0, 0, "", 0),
	("B03", "Nota de Débito", 1, 1, 0, "Débito", 0),
	("B04", "Nota de Crédito", 1, 1, 0, "Crédito", 0),
	("B11", "Comprobante de Compras", 0, 1, 1, "", 0),
	("B12", "Registro Único de Ingresos", 1, 0, 0, "", 0),
	("B13", "Comprobante para Gastos Menores", 0, 1, 1, "", 0),
	("B14", "Comprobante para Regímenes Especiales", 1, 1, 0, "", 1),
	("B15", "Comprobante Gubernamental", 1, 1, 0, "", 1),
	("B16", "Comprobante para Exportaciones", 1, 0, 0, "", 0),
	("B17", "Comprobante para Pagos al Exterior", 0, 1, 1, "", 0),
	("E31", "Factura de Crédito Fiscal Electrónica", 1, 1, 0, "", 1),
	("E32", "Factura de Consumo Electrónica", 1, 0, 0, "", 0),
	("E33", "Nota de Débito Electrónica", 1, 1, 0, "Débito", 0),
	("E34", "Nota de Crédito Electrónica", 1, 1, 0, "Crédito", 0),
	("E41", "Comprobante Electrónico de Compras", 0, 1, 1, "", 0),
	("E43", "Comprobante Electrónico para Gastos Menores", 0, 1, 1, "", 0),
	("E44", "Comprobante Electrónico para Regímenes Especiales", 1, 1, 0, "", 1),
	("E45", "Comprobante Electrónico Gubernamental", 1, 1, 0, "", 1),
	("E46", "Comprobante Electrónico para Exportaciones", 1, 0, 0, "", 0),
	("E47", "Comprobante Electrónico para Pagos al Exterior", 0, 1, 1, "", 0),
]

# Formato 607: tipo de ingreso
TIPOS_INGRESO = [
	"01 - Ingresos por operaciones (No financieros)",
	"02 - Ingresos financieros",
	"03 - Ingresos extraordinarios",
	"04 - Ingresos por arrendamientos",
	"05 - Ingresos por venta de activo depreciable",
	"06 - Otros ingresos",
]

# Formato 606: tipo de bienes y servicios comprados
TIPOS_BIENES_SERVICIOS = [
	"01 - Gastos de personal",
	"02 - Gastos por trabajos, suministros y servicios",
	"03 - Arrendamientos",
	"04 - Gastos de activos fijos",
	"05 - Gastos de representación",
	"06 - Otras deducciones admitidas",
	"07 - Gastos financieros",
	"08 - Gastos extraordinarios",
	"09 - Compras y gastos que formarán parte del costo de venta",
	"10 - Adquisiciones de activos",
	"11 - Gastos de seguros",
]

# Formato 608: tipo de anulación
TIPOS_ANULACION = [
	"01 - Deterioro de factura pre-imprenta",
	"02 - Errores de impresión (factura pre-imprenta)",
	"03 - Impresión defectuosa",
	"04 - Corrección de la información",
	"05 - Cambio de productos",
	"06 - Devolución de productos",
	"07 - Omisión de productos",
	"08 - Errores en secuencia de NCF",
	"09 - Por cese de operaciones",
	"10 - Pérdida o hurto de talonarios",
]

TIPOS_IDENTIFICACION = ["RNC", "Cédula", "Pasaporte"]

# Formato 606: tipo de retención en ISR
TIPOS_RETENCION_ISR = [
	"01 - Alquileres",
	"02 - Honorarios por servicios",
	"03 - Otras rentas",
	"04 - Otras rentas (rentas presuntas)",
	"05 - Intereses pagados a personas jurídicas residentes",
	"06 - Intereses pagados a personas físicas residentes",
	"07 - Retención por proveedores del Estado",
	"08 - Juegos telefónicos",
	"09 - Retenciones subsector de ganadería de carne bovina",
]

# Forma de pago de un Modo de Pago. Define la columna del 607 y el código del 606.
EFECTIVO = "Efectivo"
CHEQUE_TRANSFERENCIA = "Cheque / Transferencia / Depósito"
TARJETA = "Tarjeta de crédito / débito"
BONOS = "Bonos o certificados de regalo"
PERMUTA = "Permuta"
OTRAS_FORMAS = "Otras formas"
FORMAS_PAGO = [EFECTIVO, CHEQUE_TRANSFERENCIA, TARJETA, BONOS, PERMUTA, OTRAS_FORMAS]

# Formato 609: tipo y detalle del servicio adquirido en el exterior
TIPOS_SERVICIO_EXTERIOR = [
	"01 - Gastos de personal",
	"02 - Gastos por trabajos, suministros y servicios",
	"03 - Arrendamientos",
	"04 - Gastos de activos fijos",
	"05 - Gastos de representación",
	"06 - Gastos financieros",
	"07 - Gastos de seguros",
	"08 - Gastos por regalías y otros intangibles",
]
DETALLES_SERVICIO_EXTERIOR = [
	"11 - Sueldos y salarios",
	"12 - Otros gastos de personal",
	"21 - Honorarios por servicios profesionales (personas morales)",
	"22 - Honorarios por servicios profesionales (personas físicas)",
	"23 - Seguridad, mensajería, transporte y otros servicios (personas físicas)",
	"24 - Seguridad, mensajería, transporte y otros servicios (personas morales)",
	"31 - De inmuebles (a personas físicas)",
	"32 - De inmuebles (a personas morales)",
	"33 - Otros arrendamientos",
	"41 - Reparación",
	"42 - Mantenimiento",
	"51 - Relaciones públicas",
	"52 - Publicidad",
	"53 - Promociones",
	"54 - Otros gastos de representación",
	"61 - Por préstamos con bancos",
	"62 - Por préstamos con financieras",
	"63 - Por préstamos con personas físicas",
	"64 - Por préstamos con organismos internacionales",
	"65 - Otros gastos financieros",
	"71 - Gastos de seguros",
	"81 - Cesión / uso de marca",
	"82 - Transferencia de know-how",
	"83 - Cesión / uso de patente",
	"84 - Otras regalías",
]

# Concepto fiscal de una cuenta de impuesto: define en qué columna del 606 / 607 cae su monto
ITBIS = "ITBIS"
ITBIS_RETENIDO = "ITBIS retenido a terceros"
ISR_RETENIDO = "ISR retenido a terceros"
ITBIS_RETENIDO_POR_TERCEROS = "ITBIS retenido por terceros"
ISR_RETENIDO_POR_TERCEROS = "ISR retenido por terceros"
ISC = "Impuesto selectivo al consumo"
PROPINA_LEGAL = "Propina legal"
OTROS_IMPUESTOS = "Otros impuestos y tasas"

CONCEPTOS_FISCALES = [
	ITBIS,
	ITBIS_RETENIDO,
	ISR_RETENIDO,
	ITBIS_RETENIDO_POR_TERCEROS,
	ISR_RETENIDO_POR_TERCEROS,
	ISC,
	PROPINA_LEGAL,
	OTROS_IMPUESTOS,
]


def codigo(opcion: str | None) -> str:
	"""Extrae el código de una opción de catálogo: "02 - Gastos ..." -> "02"."""
	return (opcion or "").split(" - ", 1)[0].strip()
