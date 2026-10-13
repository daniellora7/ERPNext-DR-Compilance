"""Columnas oficiales de los formatos 606/607/608/609 y generación del archivo TXT para la OFV.

TXT: primera línea `<formato>|<RNC>|<AAAAMM>|<cantidad de registros>`, luego un registro por
línea con los campos separados por "|", montos con punto decimal y 2 decimales, fechas
AAAAMMDD y campos sin dato vacíos. Nombre: DGII_F_<formato>_<RNC>_<AAAAMM>.TXT.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_reportes import datos

# clave, etiqueta, tipo (Data = texto, Currency = monto)
COLUMNAS = {
	"606": [
		("rnc_cedula", "RNC o Cédula", "Data"),
		("tipo_id", "Tipo Id", "Data"),
		("tipo_bienes_servicios", "Tipo Bienes y Servicios", "Data"),
		("ncf", "NCF", "Data"),
		("ncf_modificado", "NCF o Documento Modificado", "Data"),
		("fecha_comprobante", "Fecha Comprobante", "Data"),
		("fecha_pago", "Fecha Pago", "Data"),
		("monto_servicios", "Monto Facturado en Servicios", "Currency"),
		("monto_bienes", "Monto Facturado en Bienes", "Currency"),
		("total_monto_facturado", "Total Monto Facturado", "Currency"),
		("itbis_facturado", "ITBIS Facturado", "Currency"),
		("itbis_retenido", "ITBIS Retenido", "Currency"),
		("itbis_proporcionalidad", "ITBIS sujeto a Proporcionalidad (Art. 349)", "Currency"),
		("itbis_costo", "ITBIS llevado al Costo", "Currency"),
		("itbis_adelantar", "ITBIS por Adelantar", "Currency"),
		("itbis_percibido", "ITBIS percibido en compras", "Currency"),
		("tipo_retencion_isr", "Tipo de Retención en ISR", "Data"),
		("monto_retencion_renta", "Monto Retención Renta", "Currency"),
		("isr_percibido", "ISR Percibido en compras", "Currency"),
		("isc", "Impuesto Selectivo al Consumo", "Currency"),
		("otros_impuestos", "Otros Impuestos/Tasas", "Currency"),
		("propina_legal", "Monto Propina Legal", "Currency"),
		("forma_pago", "Forma de Pago", "Data"),
	],
	"607": [
		("rnc_cedula", "RNC/Cédula o Pasaporte", "Data"),
		("tipo_id", "Tipo Identificación", "Data"),
		("ncf", "Número Comprobante Fiscal", "Data"),
		("ncf_modificado", "Número Comprobante Fiscal Modificado", "Data"),
		("tipo_ingreso", "Tipo de Ingreso", "Data"),
		("fecha_comprobante", "Fecha Comprobante", "Data"),
		("fecha_retencion", "Fecha de Retención", "Data"),
		("monto_facturado", "Monto Facturado", "Currency"),
		("itbis_facturado", "ITBIS Facturado", "Currency"),
		("itbis_retenido_terceros", "ITBIS Retenido por Terceros", "Currency"),
		("itbis_percibido", "ITBIS Percibido", "Currency"),
		("retencion_renta_terceros", "Retención Renta por Terceros", "Currency"),
		("isr_percibido", "ISR Percibido", "Currency"),
		("isc", "Impuesto Selectivo al Consumo", "Currency"),
		("otros_impuestos", "Otros Impuestos/Tasas", "Currency"),
		("propina_legal", "Monto Propina Legal", "Currency"),
		("efectivo", "Efectivo", "Currency"),
		("cheque_transferencia", "Cheque/Transferencia/Depósito", "Currency"),
		("tarjeta", "Tarjeta Débito/Crédito", "Currency"),
		("venta_credito", "Venta a Crédito", "Currency"),
		("bonos", "Bonos o Certificados de Regalo", "Currency"),
		("permuta", "Permuta", "Currency"),
		("otras_formas", "Otras Formas de Ventas", "Currency"),
	],
	"608": [
		("ncf", "Número de Comprobante Fiscal", "Data"),
		("fecha_comprobante", "Fecha de Comprobante", "Data"),
		("tipo_anulacion", "Tipo de Anulación", "Data"),
	],
	"609": [
		("razon_social", "Razón Social", "Data"),
		("tipo_id_tributaria", "Tipo ID Tributaria", "Data"),
		("id_tributaria", "ID Tributaria", "Data"),
		("pais_destino", "País de Destino", "Data"),
		("tipo_servicio", "Tipo de Servicio Adquirido", "Data"),
		("detalle_servicio", "Detalle del Servicio Adquirido", "Data"),
		("parte_relacionada", "Parte Relacionada", "Data"),
		("numero_documento", "Número de Documento", "Data"),
		("fecha_documento", "Fecha de Documento", "Data"),
		("monto_facturado", "Monto Facturado", "Currency"),
		("fecha_retencion_isr", "Fecha de Retención ISR", "Data"),
		("renta_presunta", "Renta Presunta", "Currency"),
		("isr_retenido", "ISR Retenido", "Currency"),
	],
}

GENERADORES = {
	"606": datos.datos_606,
	"607": datos.datos_607,
	"608": datos.datos_608,
	"609": datos.datos_609,
}

ROLES = ("Accounts Manager", "Accounts User", "System Manager")


def obtener(formato: str, company: str, anio, mes) -> list[dict]:
	if formato not in GENERADORES:
		frappe.throw(_("Formato desconocido: {0}").format(formato))
	if not (company and cint(anio) and 1 <= cint(mes) <= 12):
		frappe.throw(_("Indique empresa, año y mes"))
	if not es_empresa_rd(company):
		frappe.throw(_("Los formatos DGII solo aplican a empresas de República Dominicana"))
	filas = GENERADORES[formato](company, cint(anio), cint(mes))
	marcar_duplicados(formato, filas)
	return filas


# Clave que la DGII no acepta repetida en un mismo envío
CLAVE_UNICA = {
	"606": ("rnc_cedula", "ncf"),
	"607": ("ncf",),
	"608": ("ncf",),
}


def marcar_duplicados(formato: str, filas: list[dict]):
	"""Agrega un aviso a los registros cuyo NCF se repite en el período (el validador de la DGII los
	rechaza). Un comprobante informado de nuevo por retención reemplaza al del mes original, así que
	solo cuenta dentro del mismo envío."""
	campos = CLAVE_UNICA.get(formato)
	if not campos:
		return
	vistos = {}
	for fila in filas:
		if formato == "607" and not fila.get("_en_txt", True):
			continue
		clave = tuple(fila.get(c) for c in campos)
		if not clave[-1]:
			continue
		vistos.setdefault(clave, []).append(fila)
	for repetidas in vistos.values():
		if len(repetidas) < 2:
			continue
		documentos = ", ".join(f["_documento"] for f in repetidas)
		for fila in repetidas:
			aviso = _("NCF duplicado en el período ({0})").format(documentos)
			fila["_avisos"] = "; ".join(a for a in (fila.get("_avisos"), aviso) if a)


def _valor(valor, tipo: str) -> str:
	if tipo == "Currency":
		return "" if valor is None else f"{abs(flt(valor)):.2f}"
	return str(valor or "").replace("|", " ").strip()


def generar_txt(formato: str, company: str, anio, mes) -> tuple[str, str]:
	"""Devuelve (nombre de archivo, contenido) del TXT para la Oficina Virtual."""
	filas = obtener(formato, company, anio, mes)
	if formato == "607":
		filas = [f for f in filas if f["_en_txt"]]
	if not filas:
		frappe.throw(
			_(
				"No hay registros para el {0} de este período. Si no tuvo operaciones, preséntelo "
				"como declaración en cero en la Oficina Virtual (Declaraciones Juradas → Declaraciones en Cero)."
			).format(formato),
			title=_("Sin registros"),
		)

	rnc = datos.rnc_empresa(company)
	if not rnc:
		frappe.throw(_("La empresa {0} no tiene RNC (ID Fiscal)").format(company))

	periodo = f"{cint(anio):04d}{cint(mes):02d}"
	columnas = COLUMNAS[formato]
	lineas = [f"{formato}|{rnc}|{periodo}|{len(filas)}"]
	for fila in filas:
		lineas.append("|".join(_valor(fila.get(clave), tipo) for clave, _etiqueta, tipo in columnas))

	return f"DGII_F_{formato}_{rnc}_{periodo}.TXT", "\r\n".join(lineas) + "\r\n"


@frappe.whitelist()
def descargar_txt(formato: str, company: str, anio, mes):
	frappe.only_for(ROLES)
	frappe.has_permission("Company", doc=company, throw=True)
	nombre, contenido = generar_txt(formato, company, anio, mes)
	frappe.response["filename"] = nombre
	frappe.response["filecontent"] = contenido.encode("utf-8")
	frappe.response["type"] = "download"


# ---------------------------------------------------------------------------
# Apoyo a los Script Reports
# ---------------------------------------------------------------------------


def columnas_reporte(formato: str) -> list[dict]:
	columnas = [
		{
			"fieldname": "_documento",
			"label": _("Documento"),
			"fieldtype": "Dynamic Link",
			"options": "_doctype",
			"width": 170,
		},
	]
	for clave, etiqueta, tipo in COLUMNAS[formato]:
		columnas.append(
			{
				"fieldname": clave,
				"label": _(etiqueta),
				"fieldtype": tipo,
				"width": 130 if tipo == "Currency" else 120,
			}
		)
	if formato == "607":
		columnas.append({"fieldname": "_en_txt", "label": _("En TXT"), "fieldtype": "Check", "width": 70})
	columnas.append({"fieldname": "_avisos", "label": _("Observaciones"), "fieldtype": "Data", "width": 320})
	columnas.append({"fieldname": "_doctype", "label": _("Tipo de documento"), "fieldtype": "Data", "hidden": 1})
	return columnas


def ejecutar_reporte(formato: str, filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio and filters.mes):
		return columnas_reporte(formato), []

	filas = obtener(formato, filters.company, filters.anio, filters.mes)
	en_txt = [f for f in filas if f.get("_en_txt", True)]
	con_avisos = sum(1 for f in filas if f.get("_avisos"))

	resumen = [
		{"label": _("Registros en el TXT"), "value": len(en_txt), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Registros con observaciones"),
			"value": con_avisos,
			"datatype": "Int",
			"indicator": "Orange" if con_avisos else "Green",
		},
	]
	mensaje = None

	if formato == "606":
		resumen += [
			_total("Total facturado", en_txt, "total_monto_facturado"),
			_total("ITBIS facturado", en_txt, "itbis_facturado"),
			_total("ITBIS retenido", en_txt, "itbis_retenido"),
			_total("ISR retenido", en_txt, "monto_retencion_renta"),
		]
	elif formato == "607":
		resumen += [
			_total("Monto facturado (TXT)", en_txt, "monto_facturado"),
			_total("ITBIS facturado (TXT)", en_txt, "itbis_facturado"),
		]
		mensaje = _mensaje_consumo(datos.resumen_consumo(filas))
	elif formato == "609":
		resumen += [
			_total("Monto pagado al exterior", en_txt, "monto_facturado"),
			_total("ISR retenido", en_txt, "isr_retenido"),
		]

	return columnas_reporte(formato), filas, mensaje, None, resumen


def _total(etiqueta: str, filas: list[dict], clave: str) -> dict:
	return {
		"label": _(etiqueta),
		"value": sum(flt(f.get(clave)) for f in filas),
		"datatype": "Currency",
		"indicator": "Blue",
	}


def _mensaje_consumo(resumen: dict) -> str:
	if not resumen["cantidad"]:
		return _("No hay facturas de consumo menores a RD$250,000 en el período (resumen de la OFV en cero).")
	filas = [
		(_("Cantidad de facturas de consumo"), f"{resumen['cantidad']}"),
		(_("Monto facturado"), resumen["monto_facturado"]),
		(_("ITBIS facturado"), resumen["itbis_facturado"]),
		(_("Impuesto selectivo"), resumen["isc"]),
		(_("Otros impuestos"), resumen["otros_impuestos"]),
		(_("Propina legal"), resumen["propina_legal"]),
		(_("Efectivo"), resumen["efectivo"]),
		(_("Cheque / transferencia / depósito"), resumen["cheque_transferencia"]),
		(_("Tarjeta débito / crédito"), resumen["tarjeta"]),
		(_("Venta a crédito"), resumen["venta_credito"]),
		(_("Bonos o certificados de regalo"), resumen["bonos"]),
		(_("Permuta"), resumen["permuta"]),
		(_("Otras formas de venta"), resumen["otras_formas"]),
	]
	celdas = "".join(
		f"<tr><td>{etiqueta}</td><td style='text-align:right'>"
		f"{valor if isinstance(valor, str) else frappe.format(valor, 'Currency')}</td></tr>"
		for etiqueta, valor in filas
	)
	return (
		f"<b>{_('Resumen General de Facturas de Consumo (F.C.) para la Oficina Virtual')}</b>"
		f"<p>{_('Las facturas de consumo menores a RD$250,000 no van en el TXT: digite estos totales en el módulo de resumen al enviar el 607.')}</p>"
		f"<table class='table table-bordered' style='max-width:520px'>{celdas}</table>"
	)
