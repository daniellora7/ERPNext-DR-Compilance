"""Registros de los formatos de envío de datos DGII 606, 607, 608 y 609 (Norma General 07-2018).

Cada función devuelve una lista de dicts con las columnas del formato en orden oficial
(ver `formatos.COLUMNAS`), más columnas internas que empiezan con "_" (documento, avisos).
Los montos están en la moneda de la empresa y siempre en positivo, como los pide la DGII.
"""

import calendar
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta, montos_impuestos
from erpnext_rd.dgii_fiscal.ncf import PAGOS_EXTERIOR, es_proveedor_exterior
from erpnext_rd.dgii_fiscal.validaciones import es_ncf_valido, limpiar_identificacion, tipo_identificacion
from erpnext_rd.dgii_reportes.paises_iso import ISO_NUMERICO

# Facturas de consumo menores a este monto no van en el 607: se resumen en la OFV (Norma 10-18)
UMBRAL_CONSUMO = 250_000
TIPOS_CONSUMO = ("B02", "E32")
# Comprobantes sin proveedor identificado: se reporta el RNC de la empresa
TIPOS_SIN_PROVEEDOR = ("B13", "E43", *PAGOS_EXTERIOR.values())

CODIGO_ID = {"RNC": "1", "Cédula": "2", "Pasaporte": "3"}

# Forma de pago -> código del 606
FORMA_606 = {
	cat.EFECTIVO: "01",
	cat.CHEQUE_TRANSFERENCIA: "02",
	cat.TARJETA: "03",
	cat.PERMUTA: "05",
	cat.BONOS: "02",
	cat.OTRAS_FORMAS: "02",
}
COMPRA_A_CREDITO = "04"
NOTA_DE_CREDITO = "06"
MIXTO = "07"

# Columnas de forma de venta del 607
COLUMNA_607 = {
	cat.EFECTIVO: "efectivo",
	cat.CHEQUE_TRANSFERENCIA: "cheque_transferencia",
	cat.TARJETA: "tarjeta",
	cat.BONOS: "bonos",
	cat.PERMUTA: "permuta",
	cat.OTRAS_FORMAS: "otras_formas",
}
FORMA_NOTA_CREDITO = "nota_credito"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def rango(anio: int, mes: int) -> tuple[date, date]:
	anio, mes = cint(anio), cint(mes)
	return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def fecha_dgii(valor) -> str:
	return getdate(valor).strftime("%Y%m%d") if valor else ""


def identificacion(numero: str | None, tipo: str | None = None) -> tuple[str, str]:
	"""(número limpio, código de tipo 1 = RNC, 2 = Cédula, 3 = Pasaporte o ID tributaria)."""
	if tipo == "Pasaporte" and numero:
		return numero.strip(), CODIGO_ID[tipo]
	tipo = tipo_identificacion(numero)
	if not tipo:
		return "", ""
	return limpiar_identificacion(numero), CODIGO_ID[tipo]


def rnc_empresa(company: str) -> str:
	return limpiar_identificacion(frappe.get_cached_value("Company", company, "tax_id"))


def _forma_de_modo(modo: str | None) -> str:
	if not modo:
		return cat.CHEQUE_TRANSFERENCIA
	datos = frappe.get_cached_value("Mode of Payment", modo, ["rd_forma_pago", "type"], as_dict=True)
	if not datos:
		return cat.OTRAS_FORMAS
	if datos.rd_forma_pago:
		return datos.rd_forma_pago
	return cat.EFECTIVO if datos.type == "Cash" else cat.CHEQUE_TRANSFERENCIA


def pagos(doctype: str, nombre: str, hasta) -> frappe._dict:
	"""Pagos aplicados a una factura hasta una fecha, según el Payment Ledger.

	Devuelve: lista de pagos (fecha, forma, monto, comprobante), fecha en que quedó saldada
	(None si aún debe algo a esa fecha) y retenciones hechas en las entradas de pago.
	"""
	filas = frappe.db.sql(
		"""
		SELECT voucher_type, voucher_no, posting_date, amount
		FROM `tabPayment Ledger Entry`
		WHERE against_voucher_type = %(dt)s AND against_voucher_no = %(name)s
			AND delinked = 0 AND posting_date <= %(hasta)s
		ORDER BY posting_date, creation
		""",
		{"dt": doctype, "name": nombre, "hasta": hasta},
		as_dict=True,
	)
	saldo = sum(flt(f.amount) for f in filas)
	lista, retenciones = [], frappe._dict(itbis=0.0, isr=0.0, fecha=None)

	for f in filas:
		if f.voucher_no == nombre and f.voucher_type == doctype:
			continue
		monto = abs(flt(f.amount))
		if f.voucher_type == "Payment Entry":
			forma = _forma_de_modo(frappe.db.get_value("Payment Entry", f.voucher_no, "mode_of_payment"))
			_retenciones_de_pago(f.voucher_no, doctype, nombre, retenciones, f.posting_date)
		elif f.voucher_type in ("Sales Invoice", "Purchase Invoice"):
			forma = FORMA_NOTA_CREDITO
		else:
			forma = cat.CHEQUE_TRANSFERENCIA
		lista.append(frappe._dict(fecha=f.posting_date, forma=forma, monto=monto, comprobante=f.voucher_no))

	saldada = bool(filas) and abs(saldo) < 0.01
	return frappe._dict(
		lista=lista,
		fecha_saldo=max((p.fecha for p in lista), default=None) if saldada else None,
		retenciones=retenciones,
	)


def _retenciones_de_pago(pago: str, doctype: str, factura: str, acumulado, fecha):
	"""Retenciones (deducciones) de una Entrada de Pago, prorrateadas a la factura."""
	deducciones = frappe.get_all(
		"Payment Entry Deduction", filters={"parent": pago}, fields=["account", "amount"]
	)
	if not deducciones:
		return
	referencias = frappe.get_all(
		"Payment Entry Reference",
		filters={"parent": pago},
		fields=["reference_doctype", "reference_name", "allocated_amount"],
	)
	total = sum(flt(r.allocated_amount) for r in referencias)
	propio = sum(
		flt(r.allocated_amount)
		for r in referencias
		if r.reference_doctype == doctype and r.reference_name == factura
	)
	if not total or not propio:
		return
	proporcion = propio / total
	de_terceros = doctype in ("Sales Invoice", "POS Invoice")

	for d in deducciones:
		concepto = concepto_de_cuenta(d.account, retencion=True, de_terceros=de_terceros)
		monto = abs(flt(d.amount)) * proporcion
		if concepto in (cat.ITBIS_RETENIDO, cat.ITBIS_RETENIDO_POR_TERCEROS):
			acumulado.itbis += monto
		elif concepto in (cat.ISR_RETENIDO, cat.ISR_RETENIDO_POR_TERCEROS):
			acumulado.isr += monto
		else:
			continue
		acumulado.fecha = max(filter(None, [acumulado.fecha, getdate(fecha)]))


def _es_bien(item_code: str | None) -> bool:
	if not item_code:
		return False
	datos = frappe.get_cached_value(
		"Item", item_code, ["rd_bien_o_servicio", "is_stock_item", "is_fixed_asset"], as_dict=True
	)
	if not datos:
		return False
	if datos.rd_bien_o_servicio:
		return datos.rd_bien_o_servicio == "Bien"
	return bool(datos.is_stock_item or datos.is_fixed_asset)


def _avisos(lista: list[str]) -> str:
	return "; ".join(a for a in lista if a)


# ---------------------------------------------------------------------------
# 606 — Compras de bienes y servicios
# ---------------------------------------------------------------------------


def datos_606(company: str, anio: int, mes: int) -> list[dict]:
	desde, hasta = rango(anio, mes)
	del_periodo = frappe.get_all(
		"Purchase Invoice",
		filters={
			"company": company,
			"docstatus": 1,
			"rd_ncf": ("is", "set"),
			"posting_date": ("between", (desde, hasta)),
		},
		pluck="name",
		order_by="posting_date, name",
	)
	# Comprobantes de meses anteriores con retenciones pagadas en este período: se informan
	# de nuevo con la fecha de pago y los montos retenidos.
	anteriores = frappe.db.sql_list(
		"""
		SELECT DISTINCT pi.name
		FROM `tabPurchase Invoice` pi
		JOIN `tabPayment Ledger Entry` ple
			ON ple.against_voucher_type = 'Purchase Invoice' AND ple.against_voucher_no = pi.name
			AND ple.voucher_no != pi.name AND ple.delinked = 0
		WHERE pi.company = %(company)s AND pi.docstatus = 1 AND IFNULL(pi.rd_ncf, '') != ''
			AND pi.posting_date < %(desde)s AND ple.posting_date BETWEEN %(desde)s AND %(hasta)s
		""",
		{"company": company, "desde": desde, "hasta": hasta},
	)

	filas = []
	for nombre in del_periodo:
		filas.append(_fila_606(frappe.get_doc("Purchase Invoice", nombre), desde, hasta))
	for nombre in anteriores:
		fila = _fila_606(frappe.get_doc("Purchase Invoice", nombre), desde, hasta, solo_retenciones=True)
		if fila:
			filas.append(fila)
	return filas


def _fila_606(doc, desde, hasta, solo_retenciones=False) -> dict | None:
	impuestos = montos_impuestos(doc)
	estado_pago = pagos(doc.doctype, doc.name, hasta)
	retenido_itbis = impuestos.itbis_retenido + estado_pago.retenciones.itbis
	retenido_isr = impuestos.isr_retenido + estado_pago.retenciones.isr

	if cint(doc.is_paid):
		fecha_pago = doc.posting_date
		formas = {_forma_de_modo(doc.mode_of_payment)}
	else:
		fecha_pago = estado_pago.fecha_saldo
		formas = {p.forma for p in estado_pago.lista}

	if solo_retenciones and not (
		(retenido_itbis or retenido_isr) and fecha_pago and desde <= getdate(fecha_pago) <= hasta
	):
		return None

	# Las retenciones se informan cuando se pagan (fecha de pago obligatoria)
	if not fecha_pago:
		pendiente = retenido_itbis or retenido_isr
		retenido_itbis = retenido_isr = 0.0
	else:
		pendiente = 0

	if not formas:
		forma = COMPRA_A_CREDITO
	elif len(formas) > 1:
		forma = MIXTO
	else:
		unica = next(iter(formas))
		forma = NOTA_DE_CREDITO if unica == FORMA_NOTA_CREDITO else FORMA_606[unica]
	if not fecha_pago and formas:
		forma = COMPRA_A_CREDITO if not doc.is_return else forma

	if doc.rd_tipo_comprobante in TIPOS_SIN_PROVEEDOR or es_proveedor_exterior(
		frappe.get_cached_value("Supplier", doc.supplier, "country")
	):
		numero, tipo_id = identificacion(rnc_empresa(doc.company))
	else:
		numero, tipo_id = identificacion(doc.tax_id)

	servicios = bienes = 0.0
	for item in doc.items:
		if _es_bien(item.item_code):
			bienes += abs(flt(item.base_net_amount))
		else:
			servicios += abs(flt(item.base_net_amount))

	avisos = [
		_("RNC / Cédula del proveedor inválido") if tipo_id not in ("1", "2") else "",
		_("NCF inválido") if not es_ncf_valido(doc.rd_ncf) else "",
		_("Falta tipo de bienes y servicios") if not doc.rd_tipo_bienes_servicios else "",
		_("Falta tipo de retención ISR") if retenido_isr and not doc.rd_tipo_retencion_isr else "",
		_("Retención pendiente de pago: se informará en el mes en que se pague") if pendiente else "",
		_("Informado de nuevo por retención pagada en este período") if solo_retenciones else "",
	]

	return {
		"rnc_cedula": numero,
		"tipo_id": tipo_id,
		"tipo_bienes_servicios": cat.codigo(doc.rd_tipo_bienes_servicios),
		"ncf": doc.rd_ncf,
		"ncf_modificado": doc.rd_ncf_modificado or "",
		"fecha_comprobante": fecha_dgii(doc.bill_date or doc.posting_date),
		"fecha_pago": fecha_dgii(fecha_pago) if (retenido_itbis or retenido_isr or fecha_pago) else "",
		"monto_servicios": servicios,
		"monto_bienes": bienes,
		"total_monto_facturado": servicios + bienes,
		"itbis_facturado": impuestos.itbis,
		"itbis_retenido": retenido_itbis,
		"itbis_proporcionalidad": 0.0,
		"itbis_costo": impuestos.itbis_costo,
		"itbis_adelantar": impuestos.itbis - impuestos.itbis_costo,
		"itbis_percibido": None,
		"tipo_retencion_isr": cat.codigo(doc.rd_tipo_retencion_isr) if retenido_isr else "",
		"monto_retencion_renta": retenido_isr,
		"isr_percibido": None,
		"isc": impuestos.isc,
		"otros_impuestos": impuestos.otros,
		"propina_legal": impuestos.propina,
		"forma_pago": forma,
		"_doctype": doc.doctype,
		"_documento": doc.name,
		"_proveedor": doc.supplier_name,
		"_tipo_comprobante": doc.rd_tipo_comprobante,
		"_nota_credito": bool(cint(doc.is_return)),
		"_reinformado": solo_retenciones,
		"_avisos": _avisos(avisos),
	}


# ---------------------------------------------------------------------------
# 607 — Ventas de bienes y servicios
# ---------------------------------------------------------------------------


def datos_607(company: str, anio: int, mes: int) -> list[dict]:
	"""Incluye la columna interna `_en_txt`: las facturas de consumo menores al umbral no van
	en el TXT, se resumen en la Oficina Virtual (ver `resumen_consumo`)."""
	desde, hasta = rango(anio, mes)
	filas = []
	for doctype in ("Sales Invoice", "POS Invoice"):
		for nombre in frappe.get_all(
			doctype,
			filters={
				"company": company,
				"docstatus": 1,
				"rd_ncf": ("is", "set"),
				"posting_date": ("between", (desde, hasta)),
			},
			pluck="name",
			order_by="posting_date, name",
		):
			filas.append(_fila_607(frappe.get_doc(doctype, nombre), hasta))

	anteriores = frappe.db.sql(
		"""
		SELECT DISTINCT si.name
		FROM `tabSales Invoice` si
		JOIN `tabPayment Ledger Entry` ple
			ON ple.against_voucher_type = 'Sales Invoice' AND ple.against_voucher_no = si.name
			AND ple.voucher_type = 'Payment Entry' AND ple.delinked = 0
		WHERE si.company = %(company)s AND si.docstatus = 1 AND IFNULL(si.rd_ncf, '') != ''
			AND si.posting_date < %(desde)s AND ple.posting_date BETWEEN %(desde)s AND %(hasta)s
		""",
		{"company": company, "desde": desde, "hasta": hasta},
		pluck=True,
	)
	for nombre in anteriores:
		fila = _fila_607(frappe.get_doc("Sales Invoice", nombre), hasta, desde_retencion=desde)
		if fila:
			filas.append(fila)
	return filas


def _fila_607(doc, hasta, desde_retencion=None) -> dict | None:
	impuestos = montos_impuestos(doc)
	estado_pago = pagos(doc.doctype, doc.name, hasta) if doc.doctype == "Sales Invoice" else None
	retenciones = estado_pago.retenciones if estado_pago else frappe._dict(itbis=0.0, isr=0.0, fecha=None)

	if desde_retencion and not (
		(retenciones.itbis or retenciones.isr) and retenciones.fecha and retenciones.fecha >= desde_retencion
	):
		return None

	total = abs(flt(doc.base_grand_total))
	formas = dict.fromkeys(COLUMNA_607.values(), 0.0)
	cobrado = 0.0

	# Cobros en la propia factura (POS / pago al contado), sin el cambio devuelto
	cambio = abs(flt(doc.get("base_change_amount")))
	for pago in doc.get("payments") or []:
		monto = abs(flt(pago.base_amount))
		forma = _forma_de_modo(pago.mode_of_payment)
		if forma == cat.EFECTIVO and cambio:
			descuento = min(cambio, monto)
			monto -= descuento
			cambio -= descuento
		formas[COLUMNA_607[forma]] += monto
		cobrado += monto

	if estado_pago:
		for pago in estado_pago.lista:
			if pago.forma == FORMA_NOTA_CREDITO:
				continue  # una nota de crédito aplicada no es cobro: queda como venta a crédito
			formas[COLUMNA_607[pago.forma]] += pago.monto
			cobrado += pago.monto

	if cobrado > total:
		_ajustar(formas, total)
		cobrado = total
	credito = total - cobrado

	numero, tipo_id = identificacion(
		doc.tax_id, frappe.get_cached_value("Customer", doc.customer, "rd_tipo_identificacion")
	)
	if doc.rd_tipo_comprobante in ("B12",):
		numero, tipo_id = identificacion(rnc_empresa(doc.company))

	monto = abs(flt(doc.base_net_total))
	en_txt = not (doc.rd_tipo_comprobante in TIPOS_CONSUMO and monto < UMBRAL_CONSUMO)
	con_retencion = bool(retenciones.itbis or retenciones.isr)

	avisos = [
		_("NCF inválido") if not es_ncf_valido(doc.rd_ncf) else "",
		_("Falta RNC / Cédula del cliente")
		if not numero and doc.rd_tipo_comprobante not in TIPOS_CONSUMO
		else "",
		_("Informado de nuevo por retención hecha en este período") if desde_retencion else "",
	]

	return {
		"rnc_cedula": numero,
		"tipo_id": tipo_id,
		"ncf": doc.rd_ncf,
		"ncf_modificado": doc.rd_ncf_modificado or "",
		"tipo_ingreso": cat.codigo(doc.rd_tipo_ingreso) or "01",
		"fecha_comprobante": fecha_dgii(doc.posting_date),
		"fecha_retencion": fecha_dgii(retenciones.fecha) if con_retencion else "",
		"monto_facturado": monto,
		"itbis_facturado": impuestos.itbis,
		"itbis_retenido_terceros": retenciones.itbis,
		"itbis_percibido": None,
		"retencion_renta_terceros": retenciones.isr,
		"isr_percibido": None,
		"isc": impuestos.isc,
		"otros_impuestos": impuestos.otros,
		"propina_legal": impuestos.propina,
		"efectivo": formas["efectivo"],
		"cheque_transferencia": formas["cheque_transferencia"],
		"tarjeta": formas["tarjeta"],
		"venta_credito": credito,
		"bonos": formas["bonos"],
		"permuta": formas["permuta"],
		"otras_formas": formas["otras_formas"],
		"_doctype": doc.doctype,
		"_documento": doc.name,
		"_cliente": doc.customer_name,
		"_tipo_comprobante": doc.rd_tipo_comprobante,
		"_nota_credito": bool(cint(doc.is_return)),
		"_reinformado": bool(desde_retencion),
		"_en_txt": en_txt,
		"_avisos": _avisos(avisos),
	}


def _ajustar(formas: dict, total: float):
	"""Reduce proporcionalmente las formas de cobro para que no excedan el total de la factura."""
	suma = sum(formas.values())
	if not suma:
		return
	for clave in formas:
		formas[clave] = flt(formas[clave] * total / suma, 2)


def resumen_consumo(filas: list[dict]) -> dict:
	"""Resumen de facturas de consumo menores al umbral (módulo "Resumen General de F.C." de la OFV)."""
	consumo = [f for f in filas if not f["_en_txt"]]
	claves = [
		"monto_facturado",
		"itbis_facturado",
		"isc",
		"otros_impuestos",
		"propina_legal",
		"efectivo",
		"cheque_transferencia",
		"tarjeta",
		"venta_credito",
		"bonos",
		"permuta",
		"otras_formas",
	]
	resumen = {clave: sum(flt(f[clave]) for f in consumo) for clave in claves}
	resumen["cantidad"] = len(consumo)
	return resumen


# ---------------------------------------------------------------------------
# 608 — Comprobantes anulados
# ---------------------------------------------------------------------------


def datos_608(company: str, anio: int, mes: int) -> list[dict]:
	desde, hasta = rango(anio, mes)
	filas = []
	for doctype in ("Sales Invoice", "POS Invoice", "Purchase Invoice"):
		documentos = frappe.db.sql(
			f"""
			SELECT name, rd_ncf, rd_tipo_comprobante, rd_tipo_anulacion, posting_date,
				COALESCE(rd_fecha_anulacion, DATE(modified)) AS fecha_anulacion
			FROM `tab{doctype}`
			WHERE company = %(company)s AND docstatus = 2 AND IFNULL(rd_ncf, '') != ''
				AND COALESCE(rd_fecha_anulacion, DATE(modified)) BETWEEN %(desde)s AND %(hasta)s
			ORDER BY posting_date, name
			""",
			{"company": company, "desde": desde, "hasta": hasta},
			as_dict=True,
		)
		for d in documentos:
			if doctype == "Purchase Invoice" and not frappe.get_cached_value(
				"Tipo Comprobante Fiscal", d.rd_tipo_comprobante, "emitido_por_comprador"
			):
				continue  # el NCF de un proveedor lo anula el proveedor, no la empresa
			filas.append(
				{
					"ncf": d.rd_ncf,
					"fecha_comprobante": fecha_dgii(d.posting_date),
					"tipo_anulacion": cat.codigo(d.rd_tipo_anulacion),
					"_doctype": doctype,
					"_documento": d.name,
					"_fecha_anulacion": d.fecha_anulacion,
					"_avisos": _("Falta tipo de anulación") if not d.rd_tipo_anulacion else "",
				}
			)
	return filas


# ---------------------------------------------------------------------------
# 609 — Pagos al exterior
# ---------------------------------------------------------------------------


def datos_609(company: str, anio: int, mes: int) -> list[dict]:
	desde, hasta = rango(anio, mes)
	facturas = frappe.db.sql(
		"""
		SELECT pi.name
		FROM `tabPurchase Invoice` pi
		JOIN `tabSupplier` s ON s.name = pi.supplier
		WHERE pi.company = %(company)s AND pi.docstatus = 1
			AND pi.posting_date BETWEEN %(desde)s AND %(hasta)s
			AND IFNULL(s.country, '') NOT IN ('', %(pais)s)
		ORDER BY pi.posting_date, pi.name
		""",
		{"company": company, "desde": desde, "hasta": hasta, "pais": "Dominican Republic"},
		pluck=True,
	)
	return [_fila_609(frappe.get_doc("Purchase Invoice", nombre), hasta) for nombre in facturas]


def _fila_609(doc, hasta) -> dict:
	proveedor = frappe.get_cached_value(
		"Supplier", doc.supplier, ["supplier_type", "country", "tax_id", "rd_parte_relacionada"], as_dict=True
	)
	impuestos = montos_impuestos(doc)
	estado_pago = pagos(doc.doctype, doc.name, hasta)
	isr = impuestos.isr_retenido + estado_pago.retenciones.isr
	fecha_retencion = doc.posting_date if cint(doc.is_paid) else estado_pago.fecha_saldo
	codigo_pais = frappe.get_cached_value("Country", proveedor.country, "code") or ""
	pais = ISO_NUMERICO.get(codigo_pais.upper(), "")

	avisos = [
		_("Falta tipo o detalle del servicio")
		if not (doc.rd_tipo_servicio_exterior and doc.rd_detalle_servicio_exterior)
		else "",
		_("Falta ID tributaria del proveedor") if not (doc.tax_id or proveedor.tax_id) else "",
		_("País sin código ISO") if not pais else "",
		_("ISR retenido pendiente de pago") if isr and not fecha_retencion else "",
	]

	return {
		"razon_social": doc.supplier_name,
		"tipo_id_tributaria": "1" if proveedor.supplier_type == "Individual" else "2",
		"id_tributaria": (doc.tax_id or proveedor.tax_id or "").strip(),
		"pais_destino": pais,
		"tipo_servicio": cat.codigo(doc.rd_tipo_servicio_exterior),
		"detalle_servicio": cat.codigo(doc.rd_detalle_servicio_exterior),
		"parte_relacionada": "1" if cint(proveedor.rd_parte_relacionada) else "0",
		"numero_documento": doc.bill_no or doc.rd_ncf or doc.name,
		"fecha_documento": fecha_dgii(doc.bill_date or doc.posting_date),
		"monto_facturado": abs(flt(doc.base_net_total)),
		"fecha_retencion_isr": fecha_dgii(fecha_retencion) if isr and fecha_retencion else "",
		"renta_presunta": 0.0,
		"isr_retenido": isr if fecha_retencion else 0.0,
		"_doctype": doc.doctype,
		"_documento": doc.name,
		"_fecha_retencion": fecha_retencion,
		"_avisos": _avisos(avisos),
	}
