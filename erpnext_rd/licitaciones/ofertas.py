"""Seguimiento de ofertas al Estado (Fase 10.5): del proceso de compra a una Opportunity de ERPNext.

La oportunidad lleva el estado interno de la oferta, la lista de documentos y las garantías. Los
porcentajes de las garantías vienen de *Configuracion Licitaciones* (Ley 47-25 y Decreto 52-26,
arts. 201 a 214; detalle en docs/PLAN.md, *Base legal de la 10.5 y la 10.6*). La app no presenta la
oferta: eso se hace en el Portal Transaccional.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, today

from erpnext_rd.dgii_fiscal import ncf
from erpnext_rd.licitaciones import procesos, proveedor
from erpnext_rd.rd_compliance import perfil as perfil_tributario

DOCTYPE = "Opportunity"

EVALUANDO = "Evaluando"
EN_PREPARACION = "En preparación"
PRESENTADA = "Presentada"
DESIERTO = "Desierto o cancelado"
EN_PREPARACION_O_EVALUANDO = (EVALUANDO, EN_PREPARACION)
ABIERTAS = (EVALUANDO, EN_PREPARACION, PRESENTADA)
# Estados de la DGCP en los que el proceso ya no sigue
PROCESO_TERMINADO = ("Proceso desierto", "Cancelado")

SERIEDAD = "Seriedad de la oferta"
FIEL_CUMPLIMIENTO = "Fiel cumplimiento"
ANTICIPO = "Anticipo"
VICIOS_OCULTOS = "Vicios ocultos"
FIANZA = "Fianza de aseguradora"
GARANTIA_VIGENTE = ("Emitida", "Entregada")

PENDIENTE = "Pendiente"
LISTO = "Listo"
NO_APLICA = "No aplica"
RPE_ACTIVO = "RPE activo"
CERT_DGII = "Certificación DGII"
CERT_TSS = "Certificación TSS"
CERT_MIPYME = "Certificación MIPYME"
GARANTIA_SERIEDAD = "Garantía de seriedad"

# Lista con la que empieza la configuración: (documento, obligatorio, solo MIPYME, se marca con)
DOCUMENTOS_INICIALES = (
	("Registro de Proveedor del Estado (RPE) activo", 1, 0, RPE_ACTIVO),
	("Certificación de la DGII al día", 1, 0, CERT_DGII),
	("Certificación de la TSS al día", 1, 0, CERT_TSS),
	("Certificación MIPYME del MICM", 1, 1, CERT_MIPYME),
	("Formulario de presentación de la oferta", 1, 0, ""),
	("Oferta técnica", 1, 0, ""),
	("Oferta económica", 1, 0, ""),
	("Garantía de seriedad de la oferta", 1, 0, GARANTIA_SERIEDAD),
)


# Configuración --------------------------------------------------------------------------------------


def configuracion():
	"""*Configuracion Licitaciones* con los valores por defecto de los campos que nunca se guardaron."""
	conf = frappe.get_single(procesos.CONFIGURACION)
	for df in conf.meta.fields:
		if df.default is not None and conf.get(df.fieldname) in (None, ""):
			conf.set(df.fieldname, df.default)
	return conf


def asegurar_configuracion():
	"""Una sola vez (instalación o primera migración con la 10.5): guarda los valores por defecto y la
	lista inicial de documentos. Después, lo que el usuario cambie (también vaciar la lista) se respeta."""
	if frappe.db.exists("Singles", {"doctype": procesos.CONFIGURACION, "field": "pct_seriedad"}):
		return
	conf = configuracion()
	if not conf.documentos_oferta:
		for documento, obligatorio, solo_mipyme, requisito in DOCUMENTOS_INICIALES:
			conf.append(
				"documentos_oferta",
				{
					"documento": documento,
					"obligatorio": obligatorio,
					"solo_mipyme": solo_mipyme,
					"requisito": requisito,
				},
			)
	conf.flags.ignore_permissions = True
	conf.save()


def _lineas(texto: str | None) -> set[str]:
	return {linea.strip().lower() for linea in (texto or "").splitlines() if linea.strip()}


# Creación desde el proceso ----------------------------------------------------------------------------


def _datos_perfil(company: str) -> frappe._dict:
	return (
		frappe.db.get_value(
			proveedor.DOCTYPE,
			company,
			[
				"es_mipyme",
				"estado_rpe",
				"dgii_al_dia_hasta",
				"tss_al_dia_hasta",
				"certificacion_micm",
				"vencimiento_micm",
			],
			as_dict=True,
		)
		or frappe._dict()
	)


def cliente_institucion(proceso, company: str) -> str:
	"""Cliente de la institución del proceso: el que tiene su código de unidad de compra o su nombre.

	Si no existe se crea, con el comprobante gubernamental (E45 para emisores electrónicos, si no B15).
	El RNC de la institución no viene en la API: se completa a mano antes de facturar.
	"""
	codigo = cint(proceso.codigo_unidad_compra)
	if codigo and (nombre := frappe.db.get_value("Customer", {"rd_unidad_compra_dgcp": codigo})):
		return nombre
	if nombre := frappe.db.get_value("Customer", {"customer_name": proceso.unidad_compra}):
		return nombre
	tipo = "E45" if perfil_tributario.emisor_electronico(company) else "B15"
	grupo = "Government" if frappe.db.exists("Customer Group", "Government") else None
	cliente = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": proceso.unidad_compra or proceso.name,
			"customer_type": "Company",
			"customer_group": grupo,
			"rd_unidad_compra_dgcp": codigo or None,
			"rd_tipo_comprobante": tipo if frappe.db.exists("Tipo Comprobante Fiscal", tipo) else None,
		}
	)
	cliente.flags.ignore_permissions = True
	cliente.insert()
	return cliente.name


def _tasa(desde: str, hasta: str) -> float:
	if desde == hasta:
		return 1.0
	from erpnext.setup.utils import get_exchange_rate

	return flt(get_exchange_rate(desde, hasta, today()))


def garantias_sugeridas(proceso, mipyme: bool, conf, monto: float, moneda: str) -> list[dict]:
	"""Garantías que pide la norma para el proceso (el pliego puede pedir otras)."""
	instrumento = FIANZA if mipyme else None
	filas = []
	if not mipyme and (proceso.modalidad or "").strip().lower() not in _lineas(conf.modalidades_sin_seriedad):
		filas.append({"tipo": SERIEDAD, "porcentaje": flt(conf.pct_seriedad)})

	nota_fiel = None
	umbral = flt(conf.umbral_fiel_cumplimiento_usd)
	tasa = _tasa("USD", moneda)
	if umbral and monto and tasa and monto / tasa < umbral:
		nota_fiel = _("La oferta no llega a US${0}: solo si el pliego la pide.").format(frappe.format(umbral))
	pct_fiel = conf.pct_fiel_cumplimiento_mipyme if mipyme else conf.pct_fiel_cumplimiento
	filas.append({"tipo": FIEL_CUMPLIMIENTO, "porcentaje": flt(pct_fiel), "notas": nota_fiel})

	if mipyme and flt(conf.pct_anticipo_mipyme):
		filas.append(
			{
				"tipo": ANTICIPO,
				"porcentaje": flt(conf.pct_garantia_anticipo),
				"notas": _("La MIPYME recibe {0}% de anticipo al firmar el contrato.").format(
					frappe.format(flt(conf.pct_anticipo_mipyme))
				),
			}
		)
	if "obra" in (proceso.objeto_proceso or "").lower():
		filas.append({"tipo": VICIOS_OCULTOS, "porcentaje": flt(conf.pct_vicios_ocultos)})
	for fila in filas:
		fila["instrumento"] = instrumento
	return filas


def _documentos_iniciales(conf, mipyme: bool) -> list[dict]:
	return [
		{
			"documento": d.documento,
			"obligatorio": d.obligatorio,
			"requisito": d.requisito,
			"estado": PENDIENTE,
		}
		for d in conf.documentos_oferta
		if mipyme or not d.solo_mipyme
	]


def _articulos(proceso) -> list[dict]:
	return [
		{
			"item_name": (a.descripcion_usuario or a.descripcion_articulo or proceso.name)[:140],
			"description": "\n".join(filter(None, (a.descripcion_articulo, a.descripcion_usuario))),
			"qty": flt(a.cantidad) or 1,
			"rate": flt(a.precio_unitario_estimado),
		}
		for a in proceso.articulos
	]


@frappe.whitelist(methods=["POST"])
def crear_oportunidad(codigo_proceso: str, company: str) -> str:
	"""Crea la oportunidad de la empresa para el proceso, o devuelve la que ya existe."""
	frappe.has_permission(procesos.DOCTYPE, "read", codigo_proceso, throw=True)
	frappe.has_permission(DOCTYPE, "create", throw=True)
	if not ncf.es_empresa_rd(company):
		frappe.throw(_("{0} no es una empresa de República Dominicana.").format(company))
	if existente := frappe.db.get_value(DOCTYPE, {"rd_proceso_dgcp": codigo_proceso, "company": company}):
		return existente

	proceso = frappe.get_doc(procesos.DOCTYPE, codigo_proceso)
	conf = configuracion()
	datos = _datos_perfil(company)
	mipyme = bool(cint(datos.es_mipyme))
	moneda_empresa = frappe.get_cached_value("Company", company, "default_currency")
	moneda = proceso.divisa or moneda_empresa
	monto = flt(proceso.monto_estimado)

	doc = frappe.new_doc(DOCTYPE)
	doc.update(
		{
			"opportunity_from": "Customer",
			"party_name": cliente_institucion(proceso, company),
			"company": company,
			"transaction_date": today(),
			"currency": moneda,
			"conversion_rate": _tasa(moneda, moneda_empresa) or 1,
			"opportunity_amount": monto,
			"expected_closing": getdate(proceso.fecha_fin_recepcion_ofertas)
			if proceso.fecha_fin_recepcion_ofertas
			else None,
			"title": (proceso.titulo or proceso.name)[:140],
			"rd_proceso_dgcp": proceso.name,
			"rd_estado_oferta": EVALUANDO,
			"rd_cierre_ofertas": proceso.fecha_fin_recepcion_ofertas,
			"rd_oferta_mipyme": cint(mipyme),
		}
	)
	for fila in _articulos(proceso):
		doc.append("items", fila)
	for fila in _documentos_iniciales(conf, mipyme):
		doc.append("rd_documentos_oferta", fila)
	for fila in garantias_sugeridas(proceso, mipyme, conf, monto, moneda):
		doc.append("rd_garantias", fila)
	doc.insert()
	doc.add_comment("Comment", _("Creada desde el proceso de compra {0} de la DGCP.").format(proceso.name))
	return doc.name


# Validación de la oportunidad ---------------------------------------------------------------------------


def _fecha_referencia(doc):
	"""Las certificaciones deben estar vigentes al cierre de ofertas (o hoy, si ya pasó)."""
	cierre = getdate(doc.rd_cierre_ofertas) if doc.rd_cierre_ofertas else None
	hoy = getdate(today())
	return cierre if cierre and cierre > hoy else hoy


def _vigente(fecha, referencia) -> bool:
	return bool(fecha) and getdate(fecha) >= referencia


def marcar_documentos(doc):
	"""Los documentos con «Se marca con» salen del perfil de proveedor y de las garantías de la oferta."""
	datos = _datos_perfil(doc.company)
	referencia = _fecha_referencia(doc)
	seriedad = [g for g in doc.rd_garantias if g.tipo == SERIEDAD]
	for d in doc.rd_documentos_oferta:
		if not d.requisito:
			continue
		if d.requisito == RPE_ACTIVO:
			listo = datos.estado_rpe == proveedor.ACTIVO
		elif d.requisito == CERT_DGII:
			d.vence = datos.dgii_al_dia_hasta
			listo = _vigente(d.vence, referencia)
		elif d.requisito == CERT_TSS:
			d.vence = datos.tss_al_dia_hasta
			listo = _vigente(d.vence, referencia)
		elif d.requisito == CERT_MIPYME:
			d.vence = datos.vencimiento_micm
			listo = bool(cint(datos.certificacion_micm)) and _vigente(d.vence, referencia)
		elif d.requisito == GARANTIA_SERIEDAD:
			if not seriedad:
				d.estado = NO_APLICA
				continue
			listo = all(g.estado in GARANTIA_VIGENTE for g in seriedad)
		else:
			continue
		d.estado = LISTO if listo else PENDIENTE


def calcular_garantias(doc, conf=None):
	conf = conf or configuracion()
	monto = flt(doc.rd_monto_oferta) or flt(doc.opportunity_amount)
	for g in doc.rd_garantias:
		g.currency = doc.currency
		g.base = monto * flt(conf.pct_anticipo_mipyme) / 100 if g.tipo == ANTICIPO else monto
		g.monto = flt(g.base * flt(g.porcentaje) / 100, g.precision("monto"))


def documentos_pendientes(doc) -> list[str]:
	return [d.documento for d in doc.rd_documentos_oferta if d.obligatorio and d.estado == PENDIENTE]


def validar_oportunidad(doc, method=None):
	"""doc_events: Opportunity -> validate. Solo las oportunidades de un proceso de compra."""
	if not doc.get("rd_proceso_dgcp") or not ncf.es_empresa_rd(doc.company):
		return
	if not doc.rd_estado_oferta:
		doc.rd_estado_oferta = EVALUANDO
	if not doc.rd_cierre_ofertas:
		doc.rd_cierre_ofertas = frappe.db.get_value(
			procesos.DOCTYPE, doc.rd_proceso_dgcp, "fecha_fin_recepcion_ofertas"
		)
	calcular_garantias(doc)
	marcar_documentos(doc)

	if doc.rd_oferta_mipyme and any(g.instrumento and g.instrumento != FIANZA for g in doc.rd_garantias):
		frappe.msgprint(
			_(
				"A las MIPYME solo se les puede exigir fianza de aseguradora (Ley 47-25, art. 175). "
				"Use otro instrumento solo si la empresa lo elige."
			),
			indicator="orange",
			alert=True,
		)

	if doc.rd_estado_oferta == PRESENTADA and (doc.is_new() or doc.has_value_changed("rd_estado_oferta")):
		if faltan := documentos_pendientes(doc):
			frappe.throw(
				_("Faltan documentos obligatorios de la oferta: {0}.").format(", ".join(faltan)),
				title=_("Oferta incompleta"),
			)
		doc.rd_fecha_presentacion = doc.rd_fecha_presentacion or today()


# Cambios del proceso en la DGCP -----------------------------------------------------------------------


def actualizar_desde_proceso(proceso):
	"""Después de cada descarga: el cierre de ofertas (enmiendas) y los procesos desiertos o cancelados."""
	cierre = (
		get_datetime(proceso.fecha_fin_recepcion_ofertas) if proceso.fecha_fin_recepcion_ofertas else None
	)
	for o in frappe.get_all(
		DOCTYPE,
		filters={"rd_proceso_dgcp": proceso.name},
		fields=["name", "rd_estado_oferta", "rd_cierre_ofertas"],
	):
		cambios, notas = {}, []
		anterior = get_datetime(o.rd_cierre_ofertas) if o.rd_cierre_ofertas else None
		if cierre and anterior != cierre and o.rd_estado_oferta in EN_PREPARACION_O_EVALUANDO:
			cambios["rd_cierre_ofertas"] = cierre
			if anterior:
				notas.append(
					_("La DGCP cambió el cierre de ofertas del {0} al {1}.").format(
						frappe.format(anterior, "Datetime"), frappe.format(cierre, "Datetime")
					)
				)
		if proceso.estado_proceso in PROCESO_TERMINADO and o.rd_estado_oferta in ABIERTAS:
			cambios["rd_estado_oferta"] = DESIERTO
			notas.append(_("La DGCP marcó el proceso como «{0}».").format(proceso.estado_proceso))
		if not cambios:
			continue
		frappe.db.set_value(DOCTYPE, o.name, cambios)
		oportunidad = frappe.get_doc(DOCTYPE, o.name)
		for nota in notas:
			oportunidad.add_comment("Comment", nota)


# Alertas ----------------------------------------------------------------------------------------------


def por_cerrar(company: str, ahora, dias: int) -> list:
	"""Ofertas en preparación cuyo proceso deja de recibir ofertas dentro de `dias`."""
	ofertas = frappe.get_all(
		DOCTYPE,
		filters={
			"company": company,
			"rd_estado_oferta": ("in", EN_PREPARACION_O_EVALUANDO),
			"rd_cierre_ofertas": ("between", (ahora, add_days(ahora, dias))),
		},
		fields=["name", "title", "customer_name", "rd_proceso_dgcp", "rd_cierre_ofertas", "rd_estado_oferta"],
		order_by="rd_cierre_ofertas asc",
	)
	for o in ofertas:
		o.pendientes = frappe.db.count(
			"Documento Oferta Estado",
			{"parenttype": DOCTYPE, "parent": o.name, "obligatorio": 1, "estado": PENDIENTE},
		)
	return ofertas


def garantias_por_vencer(company: str, hoy, dias: int) -> list:
	"""Garantías emitidas o entregadas que vencen dentro de `dias`."""
	nombres = frappe.get_all(
		DOCTYPE, filters={"company": company, "rd_proceso_dgcp": ("is", "set")}, pluck="name"
	)
	if not nombres:
		return []
	return frappe.get_all(
		"Garantia Oferta Estado",
		filters={
			"parenttype": DOCTYPE,
			"parent": ("in", nombres),
			"estado": ("in", GARANTIA_VIGENTE),
			"vigencia_hasta": ("between", (getdate(hoy), add_days(getdate(hoy), dias))),
		},
		fields=["parent", "tipo", "monto", "currency", "vigencia_hasta", "emisor"],
		order_by="vigencia_hasta asc",
	)
