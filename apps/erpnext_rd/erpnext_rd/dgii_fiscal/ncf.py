"""Asignación de NCF / e-NCF y validaciones fiscales en facturas de venta y compra."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from erpnext_rd.dgii_fiscal.identificacion import identificacion_valida
from erpnext_rd.dgii_fiscal.validaciones import es_ncf_valido, formatear_ncf, tipo_identificacion

NOTA_CREDITO = {"B": "B04", "E": "E34"}
NOTA_DEBITO = {"B": "B03", "E": "E33"}


# ---------------------------------------------------------------------------
# Secuencias
# ---------------------------------------------------------------------------


def tomar_siguiente_ncf(company: str, tipo_comprobante: str) -> frappe._dict:
	"""Reserva el siguiente NCF de la secuencia vigente con bloqueo de fila (SELECT ... FOR UPDATE).

	El bloqueo dura hasta el commit de la transacción del submit, así dos facturas
	simultáneas nunca reciben el mismo número.
	"""
	secuencias = frappe.db.sql(
		"""
		SELECT name, serie, desde, hasta, siguiente, fecha_vencimiento
		FROM `tabSecuencia NCF`
		WHERE company = %(company)s
			AND tipo_comprobante = %(tipo)s
			AND habilitada = 1
			AND siguiente <= hasta
			AND (fecha_vencimiento IS NULL OR fecha_vencimiento >= %(hoy)s)
		ORDER BY fecha_vencimiento IS NULL, fecha_vencimiento, desde
		LIMIT 1
		FOR UPDATE
		""",
		{"company": company, "tipo": tipo_comprobante, "hoy": nowdate()},
		as_dict=True,
	)
	if not secuencias:
		frappe.throw(
			_("No hay una Secuencia NCF habilitada y vigente del tipo {0} para la empresa {1}").format(
				tipo_comprobante, company
			),
			title=_("Sin secuencia NCF"),
		)

	seq = secuencias[0]
	ncf = formatear_ncf(seq.serie, tipo_comprobante[1:], seq.siguiente)

	siguiente = seq.siguiente + 1
	disponibles = seq.hasta - siguiente + 1
	frappe.db.set_value(
		"Secuencia NCF",
		seq.name,
		{
			"siguiente": siguiente,
			"disponibles": disponibles,
			"ultimo_ncf": ncf,
			"habilitada": 1 if disponibles > 0 else 0,
		},
		update_modified=False,
	)

	_avisar_estado_secuencia(seq, disponibles)
	return frappe._dict(ncf=ncf, vencimiento=seq.fecha_vencimiento, secuencia=seq.name)


def _avisar_estado_secuencia(seq, disponibles: int):
	config = frappe.get_cached_doc("Configuracion DGII")
	total = seq.hasta - seq.desde + 1
	usado = 100 * (total - disponibles) / total

	if disponibles == 0:
		frappe.msgprint(
			_("La secuencia {0} se agotó con este comprobante. Registre una nueva.").format(seq.name),
			title=_("Secuencia NCF agotada"),
			indicator="red",
		)
	elif usado >= flt(config.porcentaje_alerta or 80):
		frappe.msgprint(
			_("La secuencia {0} lleva {1}% usado; quedan {2} comprobantes.").format(
				seq.name, round(usado), disponibles
			),
			title=_("Secuencia NCF por agotarse"),
			indicator="orange",
		)

	dias = cint(config.dias_alerta_vencimiento or 30)
	if seq.fecha_vencimiento and getdate(seq.fecha_vencimiento) <= getdate(add_days(nowdate(), dias)):
		frappe.msgprint(
			_("La secuencia {0} vence el {1}.").format(seq.name, frappe.format(seq.fecha_vencimiento, "Date")),
			title=_("Secuencia NCF por vencer"),
			indicator="orange",
		)


def _tipo(codigo: str):
	tipo = frappe.get_cached_doc("Tipo Comprobante Fiscal", codigo)
	if not tipo.habilitado:
		frappe.throw(_("El tipo de comprobante {0} está deshabilitado").format(codigo))
	return tipo


def _ncf_original(doctype: str, return_against: str | None) -> str | None:
	if not return_against:
		return None
	return frappe.db.get_value(doctype, return_against, "rd_ncf")


def _serie_de(codigo: str | None) -> str:
	return (codigo or "")[:1] or frappe.db.get_single_value("Configuracion DGII", "serie_por_defecto") or "B"


def _no_aplica(doc) -> bool:
	"""Facturas consolidadas del cierre POS: el NCF va en cada factura POS individual."""
	return doc.doctype == "Sales Invoice" and cint(doc.get("is_pos")) and cint(doc.get("is_consolidated"))


# ---------------------------------------------------------------------------
# Factura de venta
# ---------------------------------------------------------------------------


def tipo_por_defecto_venta(doc) -> str:
	if doc.is_return or doc.get("is_debit_note"):
		original = doc.return_against and frappe.db.get_value(
			"Sales Invoice", doc.return_against, "rd_tipo_comprobante"
		)
		serie = _serie_de(original)
		return NOTA_CREDITO[serie] if doc.is_return else NOTA_DEBITO[serie]

	del_cliente = frappe.db.get_value("Customer", doc.customer, "rd_tipo_comprobante")
	if del_cliente:
		return del_cliente

	serie = _serie_de(None)
	if tipo_identificacion(doc.tax_id) in ("RNC", "Cédula") and identificacion_valida(doc.tax_id):
		return f"{serie}{'01' if serie == 'B' else '31'}"
	return f"{serie}{'02' if serie == 'B' else '32'}"


def validar_venta(doc, method=None):
	"""doc_events: Sales Invoice -> validate."""
	if _no_aplica(doc):
		doc.rd_tipo_comprobante = doc.rd_ncf = doc.rd_ncf_vencimiento = doc.rd_secuencia_ncf = None
		return

	if not doc.rd_tipo_comprobante:
		doc.rd_tipo_comprobante = tipo_por_defecto_venta(doc)
	tipo = _tipo(doc.rd_tipo_comprobante)

	if not tipo.aplica_ventas:
		frappe.throw(_("El tipo {0} no se usa en facturas de venta").format(tipo.name))

	if tipo.requiere_rnc and not identificacion_valida(doc.tax_id):
		frappe.throw(
			_("El comprobante {0} requiere que el cliente tenga RNC o Cédula válido").format(tipo.name),
			title=_("Falta RNC del cliente"),
		)

	_validar_nota(doc, tipo)

	if not doc.rd_tipo_ingreso:
		doc.rd_tipo_ingreso = "01 - Ingresos por operaciones (No financieros)"


def asignar_ncf_venta(doc, method=None):
	"""doc_events: Sales Invoice -> before_submit."""
	if _no_aplica(doc) or doc.rd_ncf:
		return
	_asignar(doc)


def antes_de_cancelar_venta(doc, method=None):
	"""doc_events: Sales Invoice -> before_cancel. El NCF anulado se reporta en el 608."""
	if doc.rd_ncf and not doc.rd_tipo_anulacion:
		frappe.throw(
			_("Indique el 'Tipo de anulación' (formato 608) antes de cancelar una factura con NCF"),
			title=_("Falta tipo de anulación"),
		)


# ---------------------------------------------------------------------------
# Factura de compra
# ---------------------------------------------------------------------------


def tipo_por_defecto_compra(doc) -> str:
	if doc.is_return:
		return NOTA_CREDITO[_serie_de(None)]

	del_proveedor = frappe.db.get_value("Supplier", doc.supplier, "rd_tipo_comprobante")
	if del_proveedor:
		return del_proveedor

	serie = _serie_de(None)
	if identificacion_valida(doc.tax_id):
		return f"{serie}{'01' if serie == 'B' else '31'}"
	# Proveedor informal sin RNC: la empresa emite el comprobante de compras
	return f"{serie}{'11' if serie == 'B' else '41'}"


def validar_compra(doc, method=None):
	"""doc_events: Purchase Invoice -> validate."""
	if not doc.rd_tipo_comprobante:
		doc.rd_tipo_comprobante = tipo_por_defecto_compra(doc)
	tipo = _tipo(doc.rd_tipo_comprobante)

	if not tipo.aplica_compras:
		frappe.throw(_("El tipo {0} no se usa en facturas de compra").format(tipo.name))

	if not doc.rd_tipo_bienes_servicios:
		doc.rd_tipo_bienes_servicios = frappe.db.get_value(
			"Supplier", doc.supplier, "rd_tipo_bienes_servicios"
		)

	_validar_nota(doc, tipo)

	if tipo.emitido_por_comprador:
		# El NCF lo genera la empresa al validar (submit)
		if doc.docstatus == 0:
			doc.rd_ncf = None
		return

	if doc.rd_ncf:
		doc.rd_ncf = doc.rd_ncf.strip().upper()
		if not es_ncf_valido(doc.rd_ncf, tipo.name):
			frappe.throw(
				_("El NCF {0} no tiene el formato de un comprobante {1}").format(doc.rd_ncf, tipo.name),
				title=_("NCF inválido"),
			)
		_validar_ncf_duplicado_compra(doc)
		if not doc.bill_no:
			doc.bill_no = doc.rd_ncf

	if not identificacion_valida(doc.tax_id):
		frappe.throw(
			_("El comprobante {0} requiere que el proveedor tenga RNC o Cédula válido").format(tipo.name),
			title=_("Falta RNC del proveedor"),
		)


def antes_de_validar_compra(doc, method=None):
	"""doc_events: Purchase Invoice -> before_submit."""
	tipo = _tipo(doc.rd_tipo_comprobante)

	if not doc.rd_tipo_bienes_servicios:
		frappe.throw(_("Indique el 'Tipo de bienes y servicios' (formato 606)"))

	if tipo.emitido_por_comprador:
		if not doc.rd_ncf:
			_asignar(doc)
		return

	if not doc.rd_ncf and frappe.db.get_single_value("Configuracion DGII", "exigir_ncf_en_compras"):
		frappe.throw(_("Indique el NCF del comprobante del proveedor"), title=_("Falta NCF"))


def _validar_ncf_duplicado_compra(doc):
	duplicada = frappe.db.get_value(
		"Purchase Invoice",
		{
			"name": ("!=", doc.name),
			"supplier": doc.supplier,
			"company": doc.company,
			"rd_ncf": doc.rd_ncf,
			"docstatus": ("<", 2),
		},
	)
	if duplicada:
		frappe.throw(
			_("El NCF {0} de este proveedor ya está registrado en {1}").format(doc.rd_ncf, duplicada),
			title=_("NCF duplicado"),
		)


# ---------------------------------------------------------------------------
# Común
# ---------------------------------------------------------------------------


def _validar_nota(doc, tipo):
	es_nota_debito = cint(doc.get("is_debit_note"))

	if tipo.nota == "Crédito" and not doc.is_return:
		frappe.throw(_("El tipo {0} solo se usa en devoluciones / notas de crédito").format(tipo.name))
	if tipo.nota == "Débito" and not es_nota_debito:
		frappe.throw(_("El tipo {0} solo se usa en notas de débito").format(tipo.name))
	if doc.is_return and tipo.nota != "Crédito":
		frappe.throw(_("Una devolución debe usar un comprobante de nota de crédito (B04 / E34)"))

	if tipo.nota:
		if not doc.rd_ncf_modificado:
			doc.rd_ncf_modificado = _ncf_original(doc.doctype, doc.return_against)
		if not doc.rd_ncf_modificado:
			frappe.throw(_("Indique el NCF modificado (NCF de la factura original)"))
		if not es_ncf_valido(doc.rd_ncf_modificado):
			frappe.throw(_("El NCF modificado {0} no es válido").format(doc.rd_ncf_modificado))


def _asignar(doc):
	reservado = tomar_siguiente_ncf(doc.company, doc.rd_tipo_comprobante)

	if frappe.db.exists(doc.doctype, {"company": doc.company, "rd_ncf": reservado.ncf, "name": ("!=", doc.name)}):
		frappe.throw(
			_("El NCF {0} ya fue usado en otro documento. Revise el campo 'Siguiente' de la secuencia {1}").format(
				reservado.ncf, reservado.secuencia
			),
			title=_("NCF duplicado"),
		)

	doc.rd_ncf = reservado.ncf
	doc.rd_ncf_vencimiento = reservado.vencimiento
	doc.rd_secuencia_ncf = reservado.secuencia
