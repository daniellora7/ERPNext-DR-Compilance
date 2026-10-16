"""Recordatorios por correo de los vencimientos fiscales y de nómina de cada empresa RD.

Una tarea diaria arma, por empresa, las obligaciones que vencen dentro de los días de aviso de
*Configuracion DGII* o el mismo día, y las secuencias NCF que piden atención (las mismas reglas del
panel). Envía un solo correo por empresa con todo lo del día, a los destinatarios configurados o,
si no hay, a los usuarios con el rol *Accounts Manager*. Las fechas que caen en sábado, domingo
o feriado se corren al siguiente día laborable, como lo hace la DGII.

No sabe si la declaración ya se presentó: es un recordatorio, no un control.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, formatdate, get_url, getdate, today

from erpnext_rd.dgii_fiscal.ncf import PAIS
from erpnext_rd.dgii_reportes import declaraciones
from erpnext_rd.nomina_rd import feriados, hrms_instalado
from erpnext_rd.rd_compliance import panel

MESES = (
	"enero",
	"febrero",
	"marzo",
	"abril",
	"mayo",
	"junio",
	"julio",
	"agosto",
	"septiembre",
	"octubre",
	"noviembre",
	"diciembre",
)
# Secuencias en estos estados se recuerdan los lunes (o cuando hay otro aviso ese día)
ESTADOS_SECUENCIA = {
	"agotada": "agotada",
	"vencida": "vencida",
	"por_agotarse": "por agotarse",
	"por_vencer": "por vencer",
}


def _periodo(anio: int, mes: int) -> str:
	return f"{MESES[mes - 1]} {anio}"


def _con_nomina(company: str, anio: int, mes: int) -> bool:
	"""Hubo recibos de nómina aprobados en el período (TSS e IR-3)."""
	if not hrms_instalado():
		return False
	inicio = date(anio, mes, 1)
	return bool(
		frappe.db.exists(
			"Salary Slip",
			{
				"company": company,
				"docstatus": 1,
				"end_date": ("between", (inicio, add_days(add_months(inicio, 1), -1))),
			},
		)
	)


def obligaciones(company: str, anio: int, mes: int) -> list[dict]:
	"""Las obligaciones del período (año, mes) de una empresa, con su fecha de vencimiento."""
	from erpnext_rd.nomina_rd import ir3, novedades

	periodo = _periodo(anio, mes)
	siguiente = add_months(date(anio, mes, 1), 1)
	lista = [
		{
			"obligacion": _("IR-17 (retenciones de ISR) de {0}").format(periodo),
			"vence": feriados.dia_habil(declaraciones.vencimiento(anio, mes, declaraciones.DIA_VENCE_IR17)),
		},
		{
			"obligacion": _("Formatos 606, 607, 608 y 609 de {0}").format(periodo),
			"vence": feriados.dia_habil(declaraciones.vencimiento(anio, mes, panel.DIA_VENCE_FORMATOS)),
		},
		{
			"obligacion": _("IT-1 (ITBIS) de {0}").format(periodo),
			"vence": feriados.dia_habil(declaraciones.vencimiento(anio, mes, declaraciones.DIA_VENCE_IT1)),
		},
	]
	if _con_nomina(company, anio, mes):
		lista += [
			{
				"obligacion": _("Pago de la TSS de {0}").format(periodo),
				"vence": novedades.tercer_dia_habil(siguiente.year, siguiente.month),
			},
			{
				"obligacion": _("IR-3 (retenciones a asalariados) de {0}").format(periodo),
				"vence": ir3.fecha_limite(anio, mes),
			},
		]
	if mes == 12 and hrms_instalado():
		from erpnext_rd.nomina_rd import ir13, regalia

		lista += [
			{
				"obligacion": _("Pago de la regalía pascual {0}").format(anio),
				"vence": regalia.fecha_limite(anio),
			},
			{
				"obligacion": _("IR-13 (resumen anual de asalariados) {0}").format(anio),
				"vence": ir13.fecha_limite(anio),
			},
		]
	return lista


def pendientes(company: str, hoy: date, dias: int) -> list[dict]:
	"""Obligaciones que vencen en `dias` días o el mismo día, con los días que faltan."""
	vistos = set()
	resultado = []
	# Vencen en el mes siguiente al período: se miran los tres últimos períodos (el IR-13 de diciembre
	# vence en marzo)
	for atras in range(1, 4):
		inicio = add_months(date(hoy.year, hoy.month, 1), -atras)
		for o in obligaciones(company, inicio.year, inicio.month):
			faltan = (getdate(o["vence"]) - hoy).days
			if faltan in (dias, 0) and o["obligacion"] not in vistos:
				vistos.add(o["obligacion"])
				resultado.append(o | {"faltan": faltan})
	# Las mensuales del mes en curso (el pago de la regalía de diciembre vence en el mismo mes)
	for o in obligaciones(company, hoy.year, hoy.month):
		faltan = (getdate(o["vence"]) - hoy).days
		if faltan in (dias, 0) and o["obligacion"] not in vistos:
			vistos.add(o["obligacion"])
			resultado.append(o | {"faltan": faltan})
	return sorted(resultado, key=lambda o: o["vence"])


def empresas_rd() -> list[str]:
	return frappe.get_all("Company", filters={"country": PAIS}, pluck="name")


def secuencias_con_aviso(company: str) -> list[dict]:
	return [s for s in panel.secuencias(company) if s["estado"] in ESTADOS_SECUENCIA]


def destinatarios() -> list[str]:
	conf = frappe.get_cached_doc("Configuracion DGII")
	correos = [
		c.strip()
		for c in (conf.recordatorios_destinatarios or "").replace(",", "\n").splitlines()
		if c.strip()
	]
	if correos:
		return correos
	usuarios = frappe.get_all(
		"Has Role", filters={"role": "Accounts Manager", "parenttype": "User"}, pluck="parent", distinct=True
	)
	return frappe.get_all(
		"User",
		filters={"name": ("in", usuarios or [""]), "enabled": 1, "user_type": "System User"},
		pluck="email",
	)


def mensaje(company: str, avisos: list[dict], secuencias: list[dict]) -> str:
	"""Correo en HTML simple, sin colores: se lee igual en cualquier cliente de correo."""
	partes = [f"<p>{_('Recordatorio de cumplimiento de {0}.').format(frappe.bold(company))}</p>"]
	if avisos:
		filas = "".join(
			"<tr><td style='padding:4px 12px 4px 0'>{}</td><td style='padding:4px 12px 4px 0'>{}</td>"
			"<td style='padding:4px 0'>{}</td></tr>".format(
				o["obligacion"],
				formatdate(o["vence"]),
				_("Vence hoy") if not o["faltan"] else _("En {0} días").format(o["faltan"]),
			)
			for o in avisos
		)
		partes.append(
			"<table><tr><th align='left'>{}</th><th align='left'>{}</th><th></th></tr>{}</table>".format(
				_("Obligación"), _("Vence"), filas
			)
		)
	if secuencias:
		items = "".join(
			"<li>{} {}: {} ({})</li>".format(
				s["tipo_comprobante"],
				s["name"],
				ESTADOS_SECUENCIA[s["estado"]],
				_("{0} disponibles").format(s["disponibles"]),
			)
			for s in secuencias
		)
		partes.append(f"<p>{_('Secuencias NCF que requieren atención:')}</p><ul>{items}</ul>")
	partes.append(
		"<p><a href='{}'>{}</a></p>".format(
			get_url("/desk/rd-compliance/panel-cumplimiento"), _("Abrir el panel de cumplimiento")
		)
	)
	return "".join(partes)


def enviar_recordatorios(hoy: date | None = None) -> int:
	"""Tarea diaria. Devuelve los correos enviados (uno por empresa con avisos)."""
	conf = frappe.get_cached_doc("Configuracion DGII")
	if not conf.recordatorios_activos:
		return 0
	hoy = getdate(hoy or today())
	dias = cint(conf.recordatorios_dias)
	correos = destinatarios()
	if not correos:
		return 0

	enviados = 0
	for company in empresas_rd():
		avisos = pendientes(company, hoy, dias)
		secuencias = secuencias_con_aviso(company) if (avisos or hoy.weekday() == 0) else []
		if not (avisos or secuencias):
			continue
		frappe.sendmail(
			recipients=correos,
			subject=_("RD Compliance: vencimientos de {0}").format(company),
			message=mensaje(company, avisos, secuencias),
			reference_doctype="Company",
			reference_name=company,
		)
		enviados += 1
	return enviados


@frappe.whitelist()
def vista_previa() -> str:
	"""Botón de Configuración DGII: muestra lo que se enviaría hoy, sin enviarlo."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	conf = frappe.get_cached_doc("Configuracion DGII")
	hoy = getdate(today())
	dias = cint(conf.recordatorios_dias)
	partes = []
	for company in empresas_rd():
		avisos = pendientes(company, hoy, dias)
		secuencias = secuencias_con_aviso(company)
		if avisos or secuencias:
			partes.append(mensaje(company, avisos, secuencias))
	proximos = [
		o
		for company in empresas_rd()
		for o in obligaciones(company, *_mes_anterior(hoy))
		if getdate(o["vence"]) >= hoy
	]
	if not partes:
		partes.append(f"<p>{_('Hoy no hay recordatorios para enviar.')}</p>")
	if proximos:
		siguiente = min(proximos, key=lambda o: o["vence"])
		partes.append(
			"<p>{}</p>".format(
				_("Próximo vencimiento: {0}, el {1}.").format(
					siguiente["obligacion"], formatdate(siguiente["vence"])
				)
			)
		)
	partes.append(
		"<p>{}</p>".format(_("Destinatarios: {0}").format(", ".join(destinatarios()) or _("ninguno")))
	)
	return "<hr>".join(partes)


def _mes_anterior(hoy: date) -> tuple[int, int]:
	anterior = add_days(date(hoy.year, hoy.month, 1), -1)
	return anterior.year, anterior.month
