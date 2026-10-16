"""Datos para los formatos de impresión fiscales (factura, recibo POS) y QR del e-CF.

Se expone a Jinja como `rd_datos_fiscales(doc)` (ver `jinja` en hooks.py).
"""

import base64
import io
from urllib.parse import urlencode

import frappe
from frappe.utils import cint, flt, format_datetime, formatdate, get_datetime, getdate

from erpnext_rd.dgii_fiscal.validaciones import tipo_identificacion
from erpnext_rd.formatos import por_documento

# e-CF de consumo (E32) por debajo de este monto usan el resumen RFCE y la consulta "FC"
UMBRAL_CONSUMO_RFCE = 250_000

HOST_TIMBRE = "https://ecf.dgii.gov.do"
HOST_TIMBRE_FC = "https://fc.dgii.gov.do"
RUTA_AMBIENTE = {"TesteCF": "testecf", "CerteCF": "certecf", "eCF": "ecf"}


def url_timbre_ecf(
	*,
	rnc_emisor: str,
	encf: str,
	monto_total: float,
	codigo_seguridad: str,
	fecha_emision=None,
	fecha_firma=None,
	rnc_comprador: str | None = None,
	ambiente: str = "TesteCF",
) -> str:
	"""URL de consulta del timbre que la DGII exige codificar en el QR del e-CF."""
	ruta = RUTA_AMBIENTE[ambiente]
	monto = f"{flt(monto_total, 2):.2f}"

	if encf.startswith("E32") and flt(monto_total) < UMBRAL_CONSUMO_RFCE:
		params = {
			"RncEmisor": rnc_emisor,
			"ENCF": encf,
			"MontoTotal": monto,
			"CodigoSeguridad": codigo_seguridad,
		}
		return f"{HOST_TIMBRE_FC}/{ruta}/ConsultaTimbreFC?{urlencode(params)}"

	params = {"RncEmisor": rnc_emisor}
	if rnc_comprador:
		params["RncComprador"] = rnc_comprador
	params |= {
		"ENCF": encf,
		"FechaEmision": getdate(fecha_emision).strftime("%d-%m-%Y"),
		"MontoTotal": monto,
		"FechaFirma": get_datetime(fecha_firma).strftime("%d-%m-%Y %H:%M:%S"),
		"CodigoSeguridad": codigo_seguridad,
	}
	return f"{HOST_TIMBRE}/{ruta}/ConsultaTimbre?{urlencode(params)}"


def qr_data_uri(texto: str, escala: int = 4) -> str:
	"""QR en SVG como data URI, para incrustarlo en el HTML / PDF."""
	import pyqrcode

	buffer = io.BytesIO()
	pyqrcode.create(texto, error="M").svg(
		buffer, scale=escala, quiet_zone=2, xmldecl=False, svgns=True, background="#ffffff"
	)
	return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


def _itbis_por_linea(doc) -> dict[str, frappe._dict]:
	"""ITBIS de cada línea a partir de item_wise_tax_details (v16)."""
	por_linea: dict[str, frappe._dict] = {}
	for d in doc.get("item_wise_tax_details") or []:
		fila = por_linea.setdefault(d.item_row, frappe._dict(monto=0.0, tasa=0.0))
		fila.monto += flt(d.amount)
		fila.tasa += flt(d.rate)
	return por_linea


def _empresa(doc) -> frappe._dict:
	company = frappe.get_cached_doc("Company", doc.company)
	return frappe._dict(
		nombre=company.company_name,
		rnc=company.tax_id,
		direccion=doc.get("company_address_display"),
		telefono=company.phone_no,
		email=company.email,
		web=company.website,
	)


@por_documento
def rd_datos_fiscales(doc) -> frappe._dict:
	tipo = (
		frappe.get_cached_doc("Tipo Comprobante Fiscal", doc.rd_tipo_comprobante)
		if doc.get("rd_tipo_comprobante")
		else None
	)
	es_electronico = bool(tipo and tipo.serie == "E")
	itbis = _itbis_por_linea(doc)

	lineas, gravado, exento = [], 0.0, 0.0
	for item in doc.items:
		impuesto = itbis.get(item.name, frappe._dict(monto=0.0, tasa=0.0))
		if impuesto.monto:
			gravado += flt(item.net_amount)
		else:
			exento += flt(item.net_amount)
		lineas.append(
			frappe._dict(
				codigo=item.item_code,
				descripcion=item.item_name,
				cantidad=item.qty,
				unidad=item.uom,
				precio=item.rate,
				descuento=flt(item.discount_amount) * flt(item.qty),
				itbis=impuesto.monto,
				tasa_itbis=impuesto.tasa,
				total=flt(item.net_amount) + impuesto.monto,
			)
		)

	datos = frappe._dict(
		titulo=(tipo.descripcion if tipo else "Factura").upper(),
		tipo=tipo.name if tipo else None,
		es_electronico=es_electronico,
		ncf=doc.get("rd_ncf"),
		ncf_vencimiento=formatdate(doc.rd_ncf_vencimiento) if doc.get("rd_ncf_vencimiento") else None,
		ncf_modificado=doc.get("rd_ncf_modificado"),
		fecha=formatdate(doc.posting_date),
		hora=str(doc.posting_time or "")[:5],
		emisor=_empresa(doc),
		comprador=frappe._dict(
			nombre=doc.customer_name,
			identificacion=doc.tax_id,
			tipo_identificacion=tipo_identificacion(doc.tax_id) or "RNC / Cédula",
			direccion=doc.get("address_display"),
		),
		lineas=lineas,
		gravado=gravado,
		exento=exento,
		subtotal=flt(doc.net_total),
		descuento=flt(doc.discount_amount),
		itbis=flt(doc.total_taxes_and_charges),
		total=flt(doc.rounded_total or doc.grand_total),
		moneda=doc.currency,
		pagos=[p for p in (doc.get("payments") or []) if flt(p.amount)],
		pagado=flt(doc.get("paid_amount")),
		cambio=flt(doc.get("change_amount")),
		codigo_seguridad=doc.get("rd_codigo_seguridad"),
		fecha_firma=format_datetime(doc.rd_fecha_firma) if doc.get("rd_fecha_firma") else None,
		qr=None,
		url_timbre=None,
	)

	# El QR solo existe cuando el e-CF ya fue firmado (código de seguridad presente)
	if es_electronico and datos.ncf and datos.codigo_seguridad and cint(doc.docstatus) == 1:
		datos.url_timbre = url_timbre_ecf(
			rnc_emisor=datos.emisor.rnc,
			rnc_comprador=datos.comprador.identificacion,
			encf=datos.ncf,
			fecha_emision=doc.posting_date,
			monto_total=datos.total,
			fecha_firma=doc.rd_fecha_firma,
			codigo_seguridad=datos.codigo_seguridad,
			ambiente=frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF",
		)
		datos.qr = qr_data_uri(datos.url_timbre)

	return datos
