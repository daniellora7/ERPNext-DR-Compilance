"""Apoyo para las declaraciones mensuales IT-1 (ITBIS) e IR-17 (otras retenciones de ISR).

No genera la declaración: resume los montos del período a partir de los mismos registros del
606, 607 y 609, para digitarlos en la Oficina Virtual. Por eso el IT-1 cuadra con lo enviado en
los formatos (la DGII cruza ambos).

- IT-1: vence el día 20 del mes siguiente. Antes hay que enviar el 606 y el 607.
- IR-17: vence el día 10 del mes siguiente. Se presenta solo si hubo retenciones.
Las retenciones se declaran en el mes en que se pagan (igual que en el 606).
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta
from erpnext_rd.dgii_reportes import datos
from erpnext_rd.dgii_reportes.formatos import obtener

TIPOS_EXPORTACION = ("B16", "E46")
DIA_VENCE_IT1 = 20
DIA_VENCE_IR17 = 10


def vencimiento(anio, mes, dia: int):
	"""Día de vencimiento en el mes siguiente al período (sin correr por feriados)."""
	inicio_siguiente = add_months(getdate(f"{cint(anio):04d}-{cint(mes):02d}-01"), 1)
	return inicio_siguiente.replace(day=dia)


def _signo(fila: dict) -> int:
	return -1 if fila.get("_nota_credito") else 1


# ---------------------------------------------------------------------------
# IT-1
# ---------------------------------------------------------------------------


def bases_por_tasa(doc) -> dict:
	"""Monto gravado de una venta por tasa de ITBIS ({18.0: base, 16.0: base}), en positivo.

	La base sale del ITBIS de cada fila de impuesto y su tasa; lo que no cubren es exento.
	"""
	bases = {}
	for fila in doc.get("taxes") or []:
		tasa = flt(fila.get("rate"))
		monto = abs(flt(fila.get("base_tax_amount_after_discount_amount") or fila.get("base_tax_amount")))
		if not (tasa and monto) or fila.get("charge_type") not in ("On Net Total", "On Item Quantity"):
			continue
		if concepto_de_cuenta(fila.account_head) != cat.ITBIS:
			continue
		bases[tasa] = bases.get(tasa, 0.0) + monto * 100 / tasa
	neto = abs(flt(doc.base_net_total))
	total = sum(bases.values())
	if total > neto and total:
		bases = {t: b * neto / total for t, b in bases.items()}
	return bases


def resumen_it1(
	company: str, anio, mes, saldo_favor_anterior=0, retenciones_tarjetas=0, filas_606=None, filas_607=None
) -> frappe._dict:
	"""`filas_606` / `filas_607`: registros ya calculados del período (el panel los reutiliza)."""
	if filas_607 is None:
		filas_607 = obtener("607", company, anio, mes)
	ventas = [f for f in filas_607 if not f["_reinformado"]]
	reinformadas = [f for f in filas_607 if f["_reinformado"]]
	compras = filas_606 if filas_606 is not None else obtener("606", company, anio, mes)

	r = frappe._dict(
		ventas_brutas=0.0,
		notas_credito=0.0,
		exportaciones=0.0,
		gravadas={},
		exentas=0.0,
		itbis_facturado=0.0,
		itbis_notas_credito=0.0,
		formas=dict.fromkeys(
			[
				"efectivo",
				"cheque_transferencia",
				"tarjeta",
				"venta_credito",
				"bonos",
				"permuta",
				"otras_formas",
			],
			0.0,
		),
		compras_bienes=0.0,
		compras_servicios=0.0,
		itbis_compras=0.0,
		itbis_costo=0.0,
		itbis_deducible=0.0,
		itbis_retenido_por_terceros=0.0,
		itbis_retenido_a_terceros=0.0,
		saldo_favor_anterior=flt(saldo_favor_anterior),
		retenciones_tarjetas=flt(retenciones_tarjetas),
	)

	for f in ventas:
		doc = frappe.get_doc(f["_doctype"], f["_documento"])
		signo = _signo(f)
		monto = flt(f["monto_facturado"])
		if signo < 0:
			r.notas_credito += monto
			r.itbis_notas_credito += flt(f["itbis_facturado"])
		else:
			r.ventas_brutas += monto
			r.itbis_facturado += flt(f["itbis_facturado"])
			for clave in r.formas:
				r.formas[clave] += flt(f[clave])

		if f["_tipo_comprobante"] in TIPOS_EXPORTACION:
			r.exportaciones += signo * monto
			continue
		bases = bases_por_tasa(doc)
		for tasa, base in bases.items():
			r.gravadas[tasa] = r.gravadas.get(tasa, 0.0) + signo * base
		r.exentas += signo * max(monto - sum(bases.values()), 0.0)
		r.itbis_retenido_por_terceros += flt(f["itbis_retenido_terceros"])

	for f in reinformadas:
		r.itbis_retenido_por_terceros += flt(f["itbis_retenido_terceros"])

	for f in compras:
		r.itbis_retenido_a_terceros += flt(f["itbis_retenido"])
		if f["_reinformado"] or f["_tipo_comprobante"] in datos.PAGOS_EXTERIOR.values():
			continue
		signo = _signo(f)
		r.compras_bienes += signo * flt(f["monto_bienes"])
		r.compras_servicios += signo * flt(f["monto_servicios"])
		r.itbis_compras += signo * flt(f["itbis_facturado"])
		r.itbis_costo += signo * flt(f["itbis_costo"])
		r.itbis_deducible += signo * flt(f["itbis_adelantar"])

	r.itbis_neto_ventas = r.itbis_facturado - r.itbis_notas_credito
	r.total_operaciones = r.ventas_brutas - r.notas_credito
	r.diferencia = r.itbis_neto_ventas - r.itbis_deducible
	r.creditos = r.itbis_retenido_por_terceros + r.retenciones_tarjetas + r.saldo_favor_anterior
	resultado = r.diferencia - r.creditos
	r.itbis_a_pagar = max(resultado, 0.0)
	r.nuevo_saldo_favor = max(-resultado, 0.0)
	r.total_a_pagar = r.itbis_a_pagar + r.itbis_retenido_a_terceros
	r.vence = vencimiento(anio, mes, DIA_VENCE_IT1)
	return r


def filas_it1(r: frappe._dict) -> list[dict]:
	filas = []

	def seccion(titulo):
		filas.append({"concepto": titulo, "indent": 0, "es_titulo": 1})

	def linea(concepto, monto, nota=""):
		filas.append({"concepto": concepto, "monto": flt(monto, 2), "nota": nota, "indent": 1})

	seccion(_("I. Ingresos por operaciones"))
	linea(
		_("Ventas del período (sin ITBIS)"), r.ventas_brutas, _("Total del 607, incluye facturas de consumo")
	)
	linea(_("Notas de crédito emitidas"), -r.notas_credito)
	linea(_("Total de operaciones"), r.total_operaciones)
	linea(_("Exportaciones de bienes y servicios"), r.exportaciones, _("B16 / E46"))
	for tasa in sorted(r.gravadas, reverse=True):
		linea(_("Operaciones gravadas al {0}%").format(f"{tasa:g}"), r.gravadas[tasa])
	linea(_("Operaciones exentas o no gravadas"), r.exentas, _("Ventas locales sin ITBIS"))

	seccion(_("Ventas por forma de cobro (Anexo A, con impuestos)"))
	etiquetas = {
		"efectivo": _("Efectivo"),
		"cheque_transferencia": _("Cheque / transferencia / depósito"),
		"tarjeta": _("Tarjeta de débito / crédito"),
		"venta_credito": _("Venta a crédito"),
		"bonos": _("Bonos o certificados de regalo"),
		"permuta": _("Permuta"),
		"otras_formas": _("Otras formas de venta"),
	}
	for clave, etiqueta in etiquetas.items():
		linea(etiqueta, r.formas[clave])

	seccion(_("II. Liquidación del ITBIS"))
	linea(_("ITBIS facturado en ventas"), r.itbis_facturado)
	linea(_("ITBIS de notas de crédito emitidas"), -r.itbis_notas_credito)
	linea(_("ITBIS pagado en compras locales"), r.itbis_compras, _("Total del 606"))
	linea(_("ITBIS llevado al costo (no deducible)"), -r.itbis_costo)
	linea(_("ITBIS pagado deducible (por adelantar)"), r.itbis_deducible)
	linea(_("Diferencia: ITBIS de ventas - ITBIS deducible"), r.diferencia)
	linea(
		_("Saldo a favor del período anterior"),
		-r.saldo_favor_anterior,
		_("Digitado en el filtro, tomado del IT-1 anterior"),
	)
	linea(
		_("ITBIS retenido por terceros (clientes)"),
		-r.itbis_retenido_por_terceros,
		_("Retenciones hechas por sus clientes en el período"),
	)
	linea(
		_("Pagos computables por retenciones Norma 08-04 (tarjetas)"),
		-r.retenciones_tarjetas,
		_("Digitado en el filtro: lo reportan las adquirentes en la OFV"),
	)
	linea(_("ITBIS a pagar"), r.itbis_a_pagar)
	linea(_("Nuevo saldo a favor"), r.nuevo_saldo_favor)

	seccion(_("III. ITBIS retenido a terceros (agente de retención)"))
	linea(
		_("ITBIS retenido a proveedores"),
		r.itbis_retenido_a_terceros,
		_("Retenciones del 606 pagadas en el período"),
	)

	seccion(_("Total a pagar"))
	linea(_("ITBIS a pagar + ITBIS retenido a terceros"), r.total_a_pagar)
	return filas


# ---------------------------------------------------------------------------
# IR-17
# ---------------------------------------------------------------------------

REMESAS_EXTERIOR = "Pagos al exterior (609)"


def resumen_ir17(company: str, anio, mes, filas_606=None, filas_609=None) -> frappe._dict:
	"""ISR retenido a terceros en el período, agrupado por tipo de retención del 606 y pagos al exterior."""
	grupos = {}

	def agregar(concepto, fila, base, isr, tercero):
		grupo = grupos.setdefault(concepto, frappe._dict(concepto=concepto, base=0.0, isr=0.0, documentos=[]))
		grupo.base += base
		grupo.isr += isr
		grupo.documentos.append(
			frappe._dict(
				doctype=fila["_doctype"], documento=fila["_documento"], tercero=tercero, base=base, isr=isr
			)
		)

	opciones = {cat.codigo(o): o for o in cat.TIPOS_RETENCION_ISR}
	if filas_606 is None:
		filas_606 = obtener("606", company, anio, mes)
	if filas_609 is None:
		filas_609 = obtener("609", company, anio, mes)

	for f in filas_606:
		isr = flt(f["monto_retencion_renta"])
		if not isr or f["_tipo_comprobante"] in datos.PAGOS_EXTERIOR.values():
			continue
		concepto = opciones.get(f["tipo_retencion_isr"]) or _("Sin tipo de retención")
		agregar(concepto, f, flt(f["total_monto_facturado"]), isr, f.get("_proveedor"))

	for f in filas_609:
		if flt(f["isr_retenido"]):
			agregar(REMESAS_EXTERIOR, f, flt(f["monto_facturado"]), flt(f["isr_retenido"]), f["razon_social"])

	lista = sorted(grupos.values(), key=lambda g: g.concepto)
	return frappe._dict(
		grupos=lista,
		total_isr=sum(g.isr for g in lista),
		total_base=sum(g.base for g in lista),
		vence=vencimiento(anio, mes, DIA_VENCE_IR17),
	)


def filas_ir17(r: frappe._dict) -> list[dict]:
	filas = []
	for g in r.grupos:
		filas.append(
			{
				"concepto": g.concepto,
				"base": flt(g.base, 2),
				"isr": flt(g.isr, 2),
				"tasa": flt(g.isr * 100 / g.base, 2) if g.base else 0,
				"indent": 0,
				"es_titulo": 1,
			}
		)
		for d in g.documentos:
			filas.append(
				{
					"concepto": d.tercero,
					"_doctype": d.doctype,
					"documento": d.documento,
					"base": flt(d.base, 2),
					"isr": flt(d.isr, 2),
					"tasa": flt(d.isr * 100 / d.base, 2) if d.base else 0,
					"indent": 1,
				}
			)
	return filas


# ---------------------------------------------------------------------------
# Script Reports
# ---------------------------------------------------------------------------


def _validar(filters) -> bool:
	return bool(filters.company and filters.anio and filters.mes)


def reporte_it1(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "concepto", "label": _("Concepto"), "fieldtype": "Data", "width": 420},
		{"fieldname": "monto", "label": _("Monto"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "nota", "label": _("Nota"), "fieldtype": "Data", "width": 380},
	]
	if not _validar(filters):
		return columnas, []

	r = resumen_it1(
		filters.company, filters.anio, filters.mes, filters.saldo_favor_anterior, filters.retenciones_tarjetas
	)
	resumen = [
		{
			"label": _("ITBIS a pagar")
			if r.itbis_a_pagar or not r.nuevo_saldo_favor
			else _("Nuevo saldo a favor"),
			"value": r.itbis_a_pagar or r.nuevo_saldo_favor,
			"datatype": "Currency",
			"indicator": "Red" if r.itbis_a_pagar else "Green",
		},
		{
			"label": _("ITBIS retenido a terceros"),
			"value": r.itbis_retenido_a_terceros,
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{"label": _("Total a pagar"), "value": r.total_a_pagar, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Vence"), "value": r.vence, "datatype": "Date", "indicator": "Blue"},
	]
	mensaje = _(
		"Resumen de apoyo para digitar el IT-1 en la Oficina Virtual. Envíe primero el 606 y el 607 del "
		"período. Vence el {0} (si es feriado o fin de semana, el siguiente día hábil). Verifique los montos "
		"con su contador antes de presentar."
	).format(frappe.format(r.vence, "Date"))
	return columnas, filas_it1(r), mensaje, None, resumen


def reporte_ir17(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "concepto", "label": _("Concepto / Tercero"), "fieldtype": "Data", "width": 360},
		{
			"fieldname": "documento",
			"label": _("Documento"),
			"fieldtype": "Dynamic Link",
			"options": "_doctype",
			"width": 170,
		},
		{"fieldname": "base", "label": _("Monto pagado (base)"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "isr", "label": _("ISR retenido"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "tasa", "label": _("Tasa efectiva %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "_doctype", "label": _("Tipo de documento"), "fieldtype": "Data", "hidden": 1},
	]
	if not _validar(filters):
		return columnas, []

	r = resumen_ir17(filters.company, filters.anio, filters.mes)
	resumen = [
		{
			"label": _("ISR retenido a terceros"),
			"value": r.total_isr,
			"datatype": "Currency",
			"indicator": "Red",
		},
		{
			"label": _("Monto pagado sujeto a retención"),
			"value": r.total_base,
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{"label": _("Vence"), "value": r.vence, "datatype": "Date", "indicator": "Blue"},
	]
	if r.grupos:
		mensaje = _(
			"Resumen de apoyo para el IR-17: ISR retenido a proveedores y pagos al exterior pagados en el "
			"período. Vence el {0} (o el siguiente día hábil). Las "
			"retribuciones complementarias no se calculan aquí."
		).format(frappe.format(r.vence, "Date"))
	else:
		mensaje = _("No hubo retenciones de ISR en el período: el IR-17 no se presenta.")
	return columnas, filas_ir17(r), mensaje, None, resumen
