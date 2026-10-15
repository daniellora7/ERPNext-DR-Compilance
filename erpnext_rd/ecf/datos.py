"""Datos del e-CF a partir de las facturas de ERPNext (nombres de los elementos del XSD de la DGII).

Se arma un dict con todos los datos posibles; `esquemas.construir` emite solo los que acepta el tipo.

- Ventas (*Sales Invoice*): E31 crédito fiscal, E32 consumo, E33 nota de débito, E34 nota de crédito,
  E44 regímenes especiales, E45 gubernamental, E46 exportaciones.
- Compras (*Purchase Invoice*): E41 compras, E43 gastos menores, E47 pagos al exterior. La empresa es
  el emisor y el proveedor va como comprador.
- Montos sin ITBIS por línea (`net_rate`, `net_amount`): el descuento global de la factura ya queda
  repartido en las líneas, así los totales cuadran con lo que contabilizó ERPNext.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, now_datetime, strip_html

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.impresion import _itbis_por_linea
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta

VERSION = "1.0"
TASAS_ITBIS = {18: 1, 16: 2, 0: 3}  # tasa -> IndicadorFacturacion (4 = exento)
EXENTO = 4
CONTADO, CREDITO, GRATUITO = 1, 2, 3
# Forma de pago de la configuración DGII del modo de pago -> código del e-CF
FORMAS_PAGO = {
	cat.EFECTIVO: 1,
	cat.CHEQUE_TRANSFERENCIA: 2,
	cat.TARJETA: 3,
	cat.BONOS: 5,
	cat.PERMUTA: 6,
	cat.OTRAS_FORMAS: 8,
}
VENTA_A_CREDITO = 4
# Nota de crédito: CodigoModificacion 3 = corrige montos del NCF modificado
CORRIGE_MONTOS = 3
DIAS_NOTA_CREDITO = 30


def tipo_ecf(doc) -> int:
	codigo = doc.get("rd_tipo_comprobante") or ""
	if not re.fullmatch(r"E\d{2}", codigo):
		frappe.throw(
			_("La factura {0} no tiene un tipo de comprobante electrónico (E31 … E47).").format(doc.name)
		)
	return int(codigo[1:])


def fecha(valor) -> str:
	return getdate(valor).strftime("%d-%m-%Y")


def monto(valor) -> str:
	return f"{flt(valor, 2):.2f}"


def precio(valor) -> str:
	texto = f"{flt(valor, 4):.4f}".rstrip("0").rstrip(".")
	return texto or "0"


def _rnc(valor) -> str | None:
	digitos = re.sub(r"\D", "", valor or "")
	return digitos if len(digitos) in (9, 11) else None


def _texto(valor, largo: int) -> str | None:
	texto = " ".join(strip_html(str(valor or "")).split())
	return texto[:largo] or None


def _direccion_empresa(doc) -> str | None:
	"""Primera línea de la dirección de la empresa en la factura o, si no tiene, la de la empresa."""
	from frappe.contacts.doctype.address.address import get_company_address

	texto = doc.get("company_address_display") or get_company_address(doc.company).company_address_display
	return _texto(re.split(r"<br\s*/?>|\n", texto or "")[0], 100)


def _emisor(doc) -> dict:
	empresa = frappe.get_cached_doc("Company", doc.company)
	return {
		"RNCEmisor": _rnc(empresa.tax_id),
		"RazonSocialEmisor": _texto(empresa.company_name, 150),
		"DireccionEmisor": _direccion_empresa(doc),
		"FechaEmision": fecha(doc.posting_date),
	}


def _indicador_bien_servicio(item) -> int:
	marcado = item.get("rd_bien_o_servicio") or frappe.get_cached_value(
		"Item", item.item_code, "rd_bien_o_servicio"
	)
	if marcado:
		return 1 if marcado == "Bien" else 2
	return 1 if cint(frappe.get_cached_value("Item", item.item_code, "is_stock_item")) else 2


def _lineas(doc) -> tuple[list[dict], dict]:
	"""Detalle y totales por tasa de ITBIS."""
	itbis = _itbis_por_linea(doc)
	totales = {"gravado": {1: 0.0, 2: 0.0, 3: 0.0}, "itbis": {1: 0.0, 2: 0.0, 3: 0.0}, "exento": 0.0}
	items = []
	for i, item in enumerate(doc.items, start=1):
		impuesto = itbis.get(item.name)
		if impuesto and (impuesto.monto or impuesto.tasa == 0):
			indicador = TASAS_ITBIS.get(round(flt(impuesto.tasa)), 1)
			totales["gravado"][indicador] += flt(item.net_amount)
			totales["itbis"][indicador] += flt(impuesto.monto)
		else:
			indicador = EXENTO
			totales["exento"] += flt(item.net_amount)
		descripcion = _texto(item.description, 1000)
		items.append(
			{
				"NumeroLinea": i,
				"IndicadorFacturacion": indicador,
				"NombreItem": _texto(item.item_name, 80),
				"IndicadorBienoServicio": _indicador_bien_servicio(item),
				"DescripcionItem": descripcion if descripcion != _texto(item.item_name, 80) else None,
				"CantidadItem": monto(abs(flt(item.qty))),
				"PrecioUnitarioItem": precio(abs(flt(item.net_rate))),
				"MontoItem": monto(abs(flt(item.net_amount))),
			}
		)
	return items, totales


def _totales(doc, totales: dict) -> dict:
	gravado = totales["gravado"]
	itbis = totales["itbis"]
	datos = {
		"MontoGravadoTotal": monto(sum(gravado.values())) if any(gravado.values()) else None,
		"MontoExento": monto(totales["exento"]) if totales["exento"] else None,
		"TotalITBIS": monto(sum(itbis.values())) if any(gravado.values()) else None,
		"MontoTotal": monto(abs(flt(doc.grand_total))),
	}
	for indicador, tasa in ((1, 18), (2, 16), (3, 0)):
		if gravado[indicador]:
			datos[f"MontoGravadoI{indicador}"] = monto(abs(gravado[indicador]))
			datos[f"ITBIS{indicador}"] = tasa
			datos[f"TotalITBIS{indicador}"] = monto(abs(itbis[indicador]))
	return datos


def _formas_pago(doc, tipo_pago: int) -> list[dict]:
	if tipo_pago == CREDITO:
		return [{"FormaPago": VENTA_A_CREDITO, "MontoPago": monto(abs(flt(doc.grand_total)))}]
	formas = {}
	for pago in doc.get("payments") or []:
		if not flt(pago.amount):
			continue
		forma = frappe.get_cached_value("Mode of Payment", pago.mode_of_payment, "rd_forma_pago")
		codigo = FORMAS_PAGO.get(forma, 8)
		formas[codigo] = (
			formas.get(codigo, 0.0) + flt(pago.amount) - (flt(doc.get("change_amount")) if codigo == 1 else 0)
		)
	return [{"FormaPago": c, "MontoPago": monto(m)} for c, m in formas.items() if m > 0][:7]


def _tipo_pago(doc) -> int:
	if not flt(doc.grand_total):
		return GRATUITO
	if (
		cint(doc.get("is_pos"))
		or not doc.get("due_date")
		or getdate(doc.due_date) <= getdate(doc.posting_date)
	):
		return CONTADO
	return CREDITO


def _referencia(doc) -> dict | None:
	if not doc.get("rd_ncf_modificado"):
		return None
	original = doc.get("return_against")
	fecha_original = (
		frappe.db.get_value(doc.doctype, original, "posting_date") if original else doc.posting_date
	)
	return {
		"NCFModificado": doc.rd_ncf_modificado,
		"FechaNCFModificado": fecha(fecha_original),
		"CodigoModificacion": CORRIGE_MONTOS,
	}, fecha_original


def _retenciones(doc, items: list[dict]) -> dict:
	"""Retenciones de ITBIS / ISR de la factura de compra, repartidas por línea según su monto."""
	itbis = isr = 0.0
	for fila in doc.get("taxes") or []:
		if fila.get("add_deduct_tax") != "Deduct":
			continue
		concepto = concepto_de_cuenta(fila.account_head, retencion=True)
		if concepto == cat.ITBIS_RETENIDO:
			itbis += abs(flt(fila.tax_amount))
		elif concepto == cat.ISR_RETENIDO:
			isr += abs(flt(fila.tax_amount))
	base = sum(flt(i["MontoItem"]) for i in items) or 1
	for i in items:
		parte = flt(i["MontoItem"]) / base
		i["Retencion"] = {
			"IndicadorAgenteRetencionoPercepcion": 1,
			"MontoITBISRetenido": monto(itbis * parte) if itbis else None,
			"MontoISRRetenido": monto(isr * parte) if isr else None,
		}
	return {
		"TotalITBISRetenido": monto(itbis) if itbis else None,
		"TotalISRRetencion": monto(isr) if isr else None,
	}


def datos_ecf(doc, fecha_firma=None) -> dict:
	"""Datos del e-CF de una factura de venta o de compra."""
	tipo = tipo_ecf(doc)
	items, totales = _lineas(doc)
	encabezado = {
		"Version": VERSION,
		"IdDoc": {
			"TipoeCF": tipo,
			"eNCF": doc.get("rd_ncf"),
			"FechaVencimientoSecuencia": fecha(doc.rd_ncf_vencimiento)
			if doc.get("rd_ncf_vencimiento")
			else None,
		},
		"Emisor": _emisor(doc),
		"Totales": _totales(doc, totales),
	}
	referencia = _referencia(doc)

	if doc.doctype == "Sales Invoice":
		tipo_pago = _tipo_pago(doc)
		encabezado["IdDoc"].update(
			{
				"IndicadorMontoGravado": 1
				if any(cint(t.get("included_in_print_rate")) for t in doc.taxes)
				else 0,
				"TipoIngresos": (doc.get("rd_tipo_ingreso") or "01")[:2],
				"TipoPago": tipo_pago,
				"FechaLimitePago": fecha(doc.due_date) if tipo_pago == CREDITO else None,
				"TablaFormasPago": {"FormaDePago": _formas_pago(doc, tipo_pago)},
			}
		)
		if tipo == 34 and referencia:
			dias = date_diff(doc.posting_date, referencia[1])
			encabezado["IdDoc"]["IndicadorNotaCredito"] = 0 if dias <= DIAS_NOTA_CREDITO else 1
		encabezado["Comprador"] = {
			"RNCComprador": _rnc(doc.get("tax_id")),
			"RazonSocialComprador": _texto(doc.customer_name, 150),
		}
	else:
		proveedor = frappe.get_cached_doc("Supplier", doc.supplier)
		encabezado["Comprador"] = {
			"RNCComprador": _rnc(proveedor.tax_id),
			"RazonSocialComprador": _texto(proveedor.supplier_name, 150),
		}
		encabezado["Totales"].update(_retenciones(doc, items))

	datos = {
		"Encabezado": encabezado,
		"DetallesItems": {"Item": items},
		"InformacionReferencia": referencia[0] if referencia else None,
		"FechaHoraFirma": (fecha_firma or now_datetime()).strftime("%d-%m-%Y %H:%M:%S"),
	}
	return datos


def datos_rfce(datos: dict, codigo_seguridad: str) -> dict:
	"""Resumen de factura de consumo (E32 menor al monto de la configuración) a partir del e-CF completo."""
	encabezado = datos["Encabezado"]
	return {
		"Encabezado": {
			"Version": VERSION,
			"IdDoc": {
				k: encabezado["IdDoc"].get(k)
				for k in ("TipoeCF", "eNCF", "TipoIngresos", "TipoPago", "TablaFormasPago")
			},
			"Emisor": encabezado["Emisor"],
			"Comprador": encabezado.get("Comprador"),
			"Totales": encabezado["Totales"],
			"CodigoSeguridadeCF": codigo_seguridad,
		}
	}
