"""Alertas de licitaciones (Fase 10.4): un correo diario por empresa con perfil de proveedor activo.

Lleva los procesos nuevos de sus rubros desde la última alerta (acotados por las palabras clave y
los montos del perfil) y los procesos de sus rubros que dejan de recibir ofertas pronto. Desde la
10.5, también sus ofertas en preparación que cierran pronto y las garantías que vencen.
"""

import unicodedata
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	flt,
	fmt_money,
	format_date,
	format_datetime,
	get_url,
	get_url_to_form,
	getdate,
	now_datetime,
)

from erpnext_rd.licitaciones import ofertas, procesos, proveedor

PUBLICADO = "Proceso publicado"
# Procesos por tabla en el correo; el resto se ve en la lista
MAXIMO_EN_CORREO = 50
CAMPOS = (
	"name",
	"titulo",
	"descripcion",
	"unidad_compra",
	"modalidad",
	"monto_estimado",
	"divisa",
	"fecha_publicacion",
	"fecha_fin_recepcion_ofertas",
	"creation",
)


def sin_tildes(texto: str | None) -> str:
	normal = unicodedata.normalize("NFD", texto or "")
	return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()


def palabras(perfil) -> list[str]:
	return [sin_tildes(p.strip()) for p in (perfil.palabras_clave or "").splitlines() if p.strip()]


def coincide(perfil, proceso) -> bool:
	"""Filtros del perfil para los procesos nuevos: palabras clave y rango de monto."""
	claves = palabras(perfil)
	if claves:
		texto = sin_tildes(f"{proceso.titulo} {proceso.descripcion}")
		if not any(c in texto for c in claves):
			return False
	monto = flt(proceso.monto_estimado)
	if monto:
		if flt(perfil.monto_minimo) and monto < flt(perfil.monto_minimo):
			return False
		if flt(perfil.monto_maximo) and monto > flt(perfil.monto_maximo):
			return False
	return True


def _de_la_empresa(company: str, filtros: dict) -> list:
	nombres = frappe.get_all(
		"Empresa Proceso DGCP",
		filters={"parenttype": procesos.DOCTYPE, "company": company},
		pluck="parent",
	)
	if not nombres:
		return []
	return frappe.get_all(
		procesos.DOCTYPE,
		filters={"name": ("in", nombres), **filtros},
		fields=list(CAMPOS),
		order_by="fecha_fin_recepcion_ofertas asc",
	)


def nuevos(perfil, desde: datetime | None) -> list:
	filtros = {"creation": (">", desde)} if desde else {}
	return [p for p in _de_la_empresa(perfil.company, filtros) if coincide(perfil, p)]


def por_cerrar(perfil, ahora: datetime, dias: int) -> list:
	return _de_la_empresa(
		perfil.company,
		{
			"estado_proceso": PUBLICADO,
			"fecha_fin_recepcion_ofertas": ("between", (ahora, add_days(ahora, dias))),
		},
	)


def destinatarios(perfil) -> list[str]:
	correos = [
		c.strip() for c in (perfil.destinatarios_alertas or "").replace(",", "\n").splitlines() if c.strip()
	]
	if correos:
		return correos
	usuarios = frappe.get_all(
		"Has Role", filters={"role": "Sales Manager", "parenttype": "User"}, pluck="parent", distinct=True
	)
	return frappe.get_all(
		"User",
		filters={"name": ("in", usuarios or [""]), "enabled": 1, "user_type": "System User"},
		pluck="email",
	)


def _tabla(lista: list, titulo: str) -> str:
	"""HTML simple, sin colores: se lee igual en cualquier cliente de correo."""
	celda = "padding:4px 12px 4px 0;vertical-align:top"
	filas = "".join(
		"<tr><td style='{c}'><a href='{url}'>{titulo}</a><br>{institucion} · {modalidad}</td>"
		"<td style='{c}'>{monto}</td><td style='{c}'>{cierre}</td></tr>".format(
			c=celda,
			url=get_url_to_form(procesos.DOCTYPE, p.name),
			titulo=frappe.utils.escape_html(p.titulo or p.name),
			institucion=frappe.utils.escape_html(p.unidad_compra or ""),
			modalidad=frappe.utils.escape_html(p.modalidad or ""),
			monto=fmt_money(p.monto_estimado, currency=p.divisa) if flt(p.monto_estimado) else "",
			cierre=format_datetime(p.fecha_fin_recepcion_ofertas, "dd/MM/yyyy HH:mm")
			if p.fecha_fin_recepcion_ofertas
			else "",
		)
		for p in lista[:MAXIMO_EN_CORREO]
	)
	mas = len(lista) - MAXIMO_EN_CORREO
	if mas > 0:
		filas += f"<tr><td colspan='3' style='{celda}'>{_('Y {0} más.').format(mas)}</td></tr>"
	return (
		f"<p><b>{titulo}</b></p><table><tr><th align='left'>{_('Proceso')}</th>"
		f"<th align='left'>{_('Monto estimado')}</th><th align='left'>{_('Recibe ofertas hasta')}</th></tr>"
		f"{filas}</table>"
	)


def _tabla_ofertas(lista: list) -> str:
	celda = "padding:4px 12px 4px 0;vertical-align:top"
	filas = "".join(
		"<tr><td style='{c}'><a href='{url}'>{titulo}</a><br>{institucion}</td><td style='{c}'>{cierre}</td>"
		"<td style='{c}'>{pendientes}</td></tr>".format(
			c=celda,
			url=get_url_to_form(ofertas.DOCTYPE, o.name),
			titulo=frappe.utils.escape_html(o.title or o.name),
			institucion=frappe.utils.escape_html(o.customer_name or ""),
			cierre=format_datetime(o.rd_cierre_ofertas, "dd/MM/yyyy HH:mm"),
			pendientes=o.pendientes or _("Ninguno"),
		)
		for o in lista[:MAXIMO_EN_CORREO]
	)
	return (
		f"<p><b>{_('Sus ofertas que cierran pronto')}</b></p><table><tr><th align='left'>{_('Oferta')}</th>"
		f"<th align='left'>{_('Recibe ofertas hasta')}</th><th align='left'>{_('Documentos pendientes')}</th></tr>"
		f"{filas}</table>"
	)


def _tabla_garantias(lista: list) -> str:
	celda = "padding:4px 12px 4px 0;vertical-align:top"
	filas = "".join(
		"<tr><td style='{c}'><a href='{url}'>{oferta}</a><br>{tipo} · {emisor}</td><td style='{c}'>{monto}</td>"
		"<td style='{c}'>{vence}</td></tr>".format(
			c=celda,
			url=get_url_to_form(ofertas.DOCTYPE, g.parent),
			oferta=frappe.utils.escape_html(g.parent),
			tipo=frappe.utils.escape_html(_(g.tipo)),
			emisor=frappe.utils.escape_html(g.emisor or ""),
			monto=fmt_money(g.monto, currency=g.currency) if flt(g.monto) else "",
			vence=format_date(g.vigencia_hasta, "dd/MM/yyyy"),
		)
		for g in lista[:MAXIMO_EN_CORREO]
	)
	return (
		f"<p><b>{_('Garantías que vencen pronto')}</b></p><table><tr><th align='left'>{_('Garantía')}</th>"
		f"<th align='left'>{_('Monto')}</th><th align='left'>{_('Vigente hasta')}</th></tr>{filas}</table>"
	)


def mensaje(
	company: str,
	lista_nuevos: list,
	lista_cierre: list,
	lista_ofertas: list | None = None,
	lista_garantias: list | None = None,
) -> str:
	partes = [f"<p>{_('Procesos de compra del Estado para {0}.').format(frappe.bold(company))}</p>"]
	if lista_ofertas:
		partes.append(_tabla_ofertas(lista_ofertas))
	if lista_garantias:
		partes.append(_tabla_garantias(lista_garantias))
	if lista_nuevos:
		partes.append(_tabla(lista_nuevos, _("Procesos nuevos de sus rubros")))
	if lista_cierre:
		partes.append(_tabla(lista_cierre, _("Dejan de recibir ofertas pronto")))
	partes.append(
		"<p><a href='{}'>{}</a></p>".format(
			get_url("/desk/proceso-compra-dgcp"), _("Ver todos los procesos de compra")
		)
	)
	partes.append(
		f"<p>{_('Fuente: datos abiertos de la DGCP. Confirme las fechas en el Portal Transaccional.')}</p>"
	)
	return "".join(partes)


def enviar_alertas(ahora: datetime | None = None) -> int:
	"""Tarea diaria. Devuelve los correos enviados (uno por empresa con algo que avisar)."""
	ahora = ahora or now_datetime()
	conf = ofertas.configuracion()
	dias = cint(conf.dias_aviso_cierre)
	dias_garantias = cint(conf.dias_aviso_garantias)
	enviados = 0
	for nombre in frappe.get_all(
		proveedor.DOCTYPE, filters={"habilitado": 1, "alertas_activas": 1}, pluck="name"
	):
		perfil = frappe.get_doc(proveedor.DOCTYPE, nombre)
		# Los procesos que ya tienen oferta de la empresa van en «Sus ofertas», no como procesos
		con_oferta = set(
			frappe.get_all(
				ofertas.DOCTYPE,
				filters={"company": perfil.company, "rd_proceso_dgcp": ("is", "set")},
				pluck="rd_proceso_dgcp",
			)
		)
		lista_nuevos = [p for p in nuevos(perfil, perfil.ultima_alerta) if p.name not in con_oferta]
		vistos = {p.name for p in lista_nuevos}
		lista_cierre = [p for p in por_cerrar(perfil, ahora, dias) if p.name not in vistos] if dias else []
		lista_ofertas = ofertas.por_cerrar(perfil.company, ahora, dias) if dias else []
		lista_garantias = (
			ofertas.garantias_por_vencer(perfil.company, getdate(ahora), dias_garantias)
			if dias_garantias
			else []
		)
		lista_cierre = [p for p in lista_cierre if p.name not in con_oferta]
		total = len(lista_nuevos) + len(lista_cierre) + len(lista_ofertas) + len(lista_garantias)
		correos = destinatarios(perfil)
		if total and correos:
			frappe.sendmail(
				recipients=correos,
				subject=_("Licitaciones del Estado: {0} avisos para {1}").format(total, perfil.company),
				message=mensaje(perfil.company, lista_nuevos, lista_cierre, lista_ofertas, lista_garantias),
				reference_doctype=proveedor.DOCTYPE,
				reference_name=perfil.name,
			)
			enviados += 1
		frappe.db.set_value(proveedor.DOCTYPE, nombre, "ultima_alerta", ahora, update_modified=False)
	return enviados
