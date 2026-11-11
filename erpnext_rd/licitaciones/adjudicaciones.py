"""Adjudicaciones y contratos (Fase 10.6).

- Los contratos que publica la DGCP (`/contratos?proceso=`) se guardan en el proceso, solo para los
  procesos con ofertas de las empresas. Con el RPE del perfil de proveedor se sabe si la oferta ganó.
- La oferta ganada pasa a *Sales Order* con el mapeo estándar de Frappe.
- Precios de referencia: lo que el Estado pagó por las mismas subclases UNSPSC (`/contratos/articulos`),
  consultado en el momento.
- Retenciones: la entidad retiene al pagar y se registra como deducción en la *Payment Entry*. Aquí
  solo se avisa si lo retenido no coincide con la configuración (apagado hasta que el contador lo confirme).
"""

import statistics

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt, fmt_money, now_datetime, today

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal import ncf
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta
from erpnext_rd.licitaciones import api_dgcp, ofertas, procesos, proveedor

GANADA = "Ganada"
PERDIDA = "Perdida"
NO_PRESENTADA = "No presentada"
# Procesos seguidos por corrida (la API permite 60 consultas por minuto; son 2 por proceso)
MAXIMO_SEGUIMIENTO = 100
CAMPOS_CONTRATO = (
	"codigo_contrato",
	"razon_social",
	"estado_contrato",
	"estado_adjudicacion",
	"metodo_pago",
	"plazo_pago_factura",
	"url_contrato",
)
# Precios de referencia
MAXIMO_SUBCLASES = 5
FILAS_POR_SUBCLASE = 50
CONTRATOS_CON_ADJUDICATARIO = 15
CACHE_HORAS = 12


# Contratos del proceso ------------------------------------------------------------------------------


def guardar_contratos(proceso, filas: list[dict]) -> bool:
	"""Reemplaza los contratos del proceso. Devuelve si cambió algo."""
	nuevos = [
		{
			**{campo: (f.get(campo) or "").strip() or None for campo in CAMPOS_CONTRATO},
			"rpe": str(f.get("rpe") or "") or None,
			"valor_contratado": flt(f.get("valor_contratado")),
			"divisa": f.get("divisa") if frappe.db.exists("Currency", f.get("divisa")) else None,
			"fecha_adjudicacion": procesos.fecha_local(f.get("fecha_adjudicacion")),
		}
		for f in filas
	]
	antes = {(c.codigo_contrato, c.estado_contrato) for c in proceso.contratos}
	despues = {(c["codigo_contrato"], c["estado_contrato"]) for c in nuevos}
	if antes == despues:
		return False
	proceso.set("contratos", nuevos)
	proceso.flags.ignore_permissions = True
	proceso.save()
	return True


def resolver(proceso):
	"""Con contratos publicados, cada oferta abierta del proceso queda ganada, perdida o no presentada."""
	if not proceso.contratos:
		return
	ganadores = {c.rpe for c in proceso.contratos if c.rpe}
	for o in frappe.get_all(
		ofertas.DOCTYPE,
		filters={"rd_proceso_dgcp": proceso.name, "rd_estado_oferta": ("in", ofertas.ABIERTAS)},
		fields=["name", "company", "rd_estado_oferta"],
	):
		rpe = frappe.db.get_value(proveedor.DOCTYPE, o.company, "rpe")
		propios = [c for c in proceso.contratos if rpe and c.rpe == rpe]
		if propios:
			estado = GANADA
			nota = _("La DGCP adjudicó a la empresa: {0}.").format(
				", ".join(
					f"{c.codigo_contrato} ({fmt_money(c.valor_contratado, currency=c.divisa)})"
					for c in propios
				)
			)
		else:
			estado = PERDIDA if o.rd_estado_oferta == ofertas.PRESENTADA else NO_PRESENTADA
			nota = _("La DGCP adjudicó el proceso a: {0}.").format(
				", ".join(sorted({c.razon_social or c.rpe or "?" for c in proceso.contratos}))
			)
			if not ganadores:
				continue
		frappe.db.set_value(ofertas.DOCTYPE, o.name, "rd_estado_oferta", estado)
		frappe.get_doc(ofertas.DOCTYPE, o.name).add_comment("Comment", nota)


def seguidos() -> list[str]:
	"""Procesos con ofertas abiertas cuyo cierre ya pasó: esperan la adjudicación."""
	nombres = set(
		frappe.get_all(
			ofertas.DOCTYPE,
			filters={"rd_proceso_dgcp": ("is", "set"), "rd_estado_oferta": ("in", ofertas.ABIERTAS)},
			pluck="rd_proceso_dgcp",
		)
	)
	if not nombres:
		return []
	return frappe.get_all(
		procesos.DOCTYPE,
		filters={"name": ("in", list(nombres)), "fecha_fin_recepcion_ofertas": ("<", now_datetime())},
		order_by="fecha_fin_recepcion_ofertas asc",
		limit=MAXIMO_SEGUIMIENTO,
		pluck="name",
	)


def seguir_adjudicaciones() -> int:
	"""Paso 4 de la sincronización: estado y contratos de los procesos con ofertas. Devuelve los revisados."""
	revisados = 0
	for codigo in seguidos():
		fila = next(iter(api_dgcp.consultar("procesos", proceso=codigo)), None)
		proceso = procesos.guardar(fila, None, {})[0] if fila else frappe.get_doc(procesos.DOCTYPE, codigo)
		guardar_contratos(proceso, api_dgcp.consultar("contratos", proceso=codigo))
		resolver(proceso)
		revisados += 1
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
	return revisados


# Oferta ganada a Sales Order --------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def crear_pedido(source_name: str, target_doc: str | None = None):
	"""Sales Order desde la oportunidad ganada (frappe.model.open_mapped_doc)."""
	oportunidad = frappe.get_doc(ofertas.DOCTYPE, source_name)
	oportunidad.check_permission("read")
	if oportunidad.rd_estado_oferta != GANADA:
		frappe.throw(_("Solo las ofertas ganadas pasan a pedido de venta."))
	if oportunidad.opportunity_from != "Customer":
		frappe.throw(_("La oportunidad no tiene un cliente."))
	contrato = _contrato_propio(oportunidad)

	def completar(origen, destino):
		destino.customer = origen.party_name
		destino.transaction_date = today()
		destino.po_no = contrato.codigo_contrato if contrato else origen.rd_proceso_dgcp
		destino.po_date = (
			contrato.fecha_adjudicacion.date() if contrato and contrato.fecha_adjudicacion else None
		)
		destino.rd_proceso_dgcp = origen.rd_proceso_dgcp
		destino.run_method("set_missing_values")

	return get_mapped_doc(
		ofertas.DOCTYPE,
		source_name,
		{
			ofertas.DOCTYPE: {"doctype": "Sales Order"},
			"Opportunity Item": {
				"doctype": "Sales Order Item",
				"field_map": {"uom": "stock_uom"},
				"add_if_empty": True,
			},
		},
		target_doc,
		completar,
	)


def _contrato_propio(oportunidad):
	rpe = frappe.db.get_value(proveedor.DOCTYPE, oportunidad.company, "rpe")
	if not rpe:
		return None
	proceso = frappe.get_doc(procesos.DOCTYPE, oportunidad.rd_proceso_dgcp)
	return next((c for c in proceso.contratos if c.rpe == rpe), None)


# Precios de referencia ----------------------------------------------------------------------------------


def _adjudicatarios(codigos: list[str]) -> dict[str, str]:
	"""{proceso: adjudicatarios} con caché (la API es lenta y estos datos casi no cambian)."""
	resultado = {}
	for codigo in codigos:
		clave = f"erpnext_rd:adjudicatarios:{codigo}"
		valor = frappe.cache.get_value(clave)
		if valor is None:
			filas = api_dgcp.consultar("contratos", proceso=codigo)
			valor = ", ".join(sorted({(f.get("razon_social") or "").strip() for f in filas} - {""}))
			frappe.cache.set_value(clave, valor, expires_in_sec=CACHE_HORAS * 3600)
		resultado[codigo] = valor
	return resultado


def _resumen_precios(filas: list[dict]) -> list[dict]:
	por_unidad = {}
	for f in filas:
		if flt(f["precio_unitario"]) > 0:
			por_unidad.setdefault(f["unidad"] or "", []).append(flt(f["precio_unitario"]))
	return [
		{
			"unidad": unidad,
			"contratos": len(precios),
			"minimo": min(precios),
			"mediana": statistics.median(precios),
			"maximo": max(precios),
		}
		for unidad, precios in sorted(por_unidad.items(), key=lambda x: -len(x[1]))
	]


@frappe.whitelist()
def precios_referencia(codigo_proceso: str) -> list[dict]:
	"""Últimos precios que pagó el Estado por las subclases UNSPSC del proceso."""
	frappe.has_permission(procesos.DOCTYPE, "read", codigo_proceso, throw=True)
	proceso = frappe.get_doc(procesos.DOCTYPE, codigo_proceso)
	subclases = {}
	for a in proceso.articulos:
		if a.subclase_unspsc and a.subclase_unspsc not in subclases:
			subclases[a.subclase_unspsc] = a.descripcion_articulo
	resultado = []
	try:
		for subclase, descripcion in list(subclases.items())[:MAXIMO_SUBCLASES]:
			filas = [
				{
					"proceso": f.get("codigo_proceso"),
					"contrato": f.get("codigo_contrato"),
					"descripcion": (
						f.get("descripcion_usuario") or f.get("descripcion_articulo") or ""
					).strip(),
					"unidad": f.get("unidad_medida"),
					"cantidad": flt(f.get("cantidad")),
					"precio_unitario": flt(f.get("precio_unitario")),
					"itbis": flt(f.get("itbis")),
					"fecha": procesos.fecha_local(f.get("fecha_creacion_contrato")),
				}
				for f in api_dgcp.consultar(
					"contratos/articulos", subclase=subclase, limit=FILAS_POR_SUBCLASE
				)
				if f.get("codigo_proceso") != codigo_proceso
			]
			con_nombre = list(dict.fromkeys(f["proceso"] for f in filas))[:CONTRATOS_CON_ADJUDICATARIO]
			nombres = _adjudicatarios(con_nombre)
			for f in filas:
				f["adjudicatario"] = nombres.get(f["proceso"])
			resultado.append(
				{
					"subclase": subclase,
					"descripcion": descripcion,
					"resumen": _resumen_precios(filas),
					"filas": filas,
				}
			)
	except (api_dgcp.ErrorAPIDGCP, OSError) as e:
		frappe.throw(_("No se pudo consultar la API de la DGCP: {0}").format(str(e)))
	return resultado


# Retenciones en los cobros ------------------------------------------------------------------------------


def _ecf_aceptado(factura: str) -> bool:
	from erpnext_rd.ecf.emision import ACEPTADOS, ENVIO

	return bool(
		frappe.db.exists(
			ENVIO, {"tipo_documento": "Sales Invoice", "documento": factura, "estado": ("in", ACEPTADOS)}
		)
	)


def _factura(nombre: str):
	return frappe.db.get_value("Sales Invoice", nombre, ["grand_total", "net_total"], as_dict=True)


def isr_esperado(doc, conf) -> float:
	"""ISR que debió retener la entidad sobre las facturas que cobra la Entrada de Pago."""
	esperado = 0.0
	for ref in doc.references:
		if ref.reference_doctype != "Sales Invoice" or not flt(ref.allocated_amount):
			continue
		if cint(conf.isr_exento_con_ecf) and _ecf_aceptado(ref.reference_name):
			continue
		factura = _factura(ref.reference_name)
		if not factura or not flt(factura.grand_total):
			continue
		base = factura.grand_total if conf.base_retencion_isr == "Con ITBIS" else factura.net_total
		esperado += (
			flt(base)
			* flt(conf.pct_retencion_isr)
			/ 100
			* flt(ref.allocated_amount)
			/ flt(factura.grand_total)
		)
	return esperado


def validar_cobro(doc, method=None):
	"""doc_events: Payment Entry -> validate. Aviso (no bloquea) en los cobros a entidades del Estado."""
	if doc.payment_type != "Receive" or doc.party_type != "Customer" or not ncf.es_empresa_rd(doc.company):
		return
	if not frappe.db.get_value("Customer", doc.party, "rd_unidad_compra_dgcp"):
		return
	conf = ofertas.configuracion()
	if not cint(conf.avisar_retenciones):
		return
	retenido = sum(
		abs(flt(d.amount))
		for d in doc.deductions
		if concepto_de_cuenta(d.account, retencion=True, de_terceros=True) == cat.ISR_RETENIDO_POR_TERCEROS
	)
	esperado = isr_esperado(doc, conf)
	moneda = frappe.get_cached_value("Company", doc.company, "default_currency")
	if abs(retenido - esperado) > flt(conf.tolerancia_retencion):
		frappe.msgprint(
			_(
				"La entidad del Estado debió retener {0} de ISR ({1}% de la factura {2}) y la Entrada de Pago "
				"registra {3}. Agregue o corrija la deducción con la cuenta de ISR retenido por terceros."
			).format(
				fmt_money(esperado, currency=moneda),
				frappe.format(flt(conf.pct_retencion_isr)),
				_(conf.base_retencion_isr).lower(),
				fmt_money(retenido, currency=moneda),
			),
			title=_("Retención del Estado"),
			indicator="orange",
		)
