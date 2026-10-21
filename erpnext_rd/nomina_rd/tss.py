"""Archivo de autodeterminación mensual (AM) de la TSS para el SUIR Plus.

Formato: «Instructivo para construcción de archivos de autodeterminación y novedades», versión 6.0
de la TSS (tss.gob.do → Documentos → Instructivos). Texto de ancho fijo con un registro de
encabezado (E), uno de detalle (D) por trabajador y un sumario (S). Cada envío sustituye al anterior
del período, por eso el archivo lleva a todos los trabajadores de la nómina.

Los montos salen de los recibos de nómina aprobados (Salary Slip de Frappe HR) cuyo período termina
en el mes:

- Salario SS: devengos cuyo componente tiene `rd_cotiza_tss` (la misma base de AFP y SFS).
- Salario ISR: devengos con `is_tax_applicable` que cotizan; solo se informa si difiere del Salario SS.
- Otras remuneraciones ISR: devengos gravados que no cotizan a la TSS.
- Ingresos exentos del ISR: regalía (código 01) y preaviso / cesantía (02) de los *Gratuity* aprobados
  del mes con regla RD; si se pagan por el recibo, esa fila no se suma al salario.
- Tipo de ingreso: el del empleado (`rd_tipo_ingreso_tss`) o, si no tiene, Normal (0001) o
  «No laboró mes completo» (0004) el mes en que entra o sale.

Documento del trabajador: cédula (C); si no tiene, NSS (N); si no, pasaporte (P). La TSS no recibe
otros documentos: un extranjero con carné u otro documento necesita el NSS que ella asigna.

Con los mismos datos se arma la rectificativa del IR-3 (RT), que se envía después de pagar la TSS y
solo recalcula el ISR. El archivo de novedades (NV) está en `novedades.py`.
"""

import re
import unicodedata
from calendar import monthrange
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion
from erpnext_rd.dgii_reportes.datos import rnc_empresa
from erpnext_rd.nomina_rd import hrms_instalado, salario
from erpnext_rd.nomina_rd.empleado import cedula_valida

PROCESO = "AM"
RECTIFICATIVA = "RT"
SIN_RECIBO = "Sin recibo de nómina aprobado en el mes: no va en el archivo"
ROLES = ("HR Manager", "HR User", "System Manager")

TIPO_CEDULA = "C"
TIPO_NSS = "N"
TIPO_PASAPORTE = "P"

NORMAL = "0001"
MES_INCOMPLETO = "0004"

REGALIA = "01"
PRESTACIONES = "02"
PENSION_ALIMENTICIA = "03"
EXENTOS_POR_PRESTACION = {"Regalía": REGALIA, "Cesantía": PRESTACIONES, "Preaviso": PRESTACIONES}

LONGITUD_DETALLE = 312
LONGITUD_CON_EXENTOS = 366
LONGITUD_RECTIFICATIVA = 258
PENSIONADO = "0006"


# ---------------------------------------------------------------------------
# Formato de los campos
# ---------------------------------------------------------------------------


def _ascii(valor) -> str:
	"""Mayúsculas sin tildes: el archivo es de ancho fijo y cada caracter debe ocupar un byte."""
	texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
	return " ".join(texto.upper().split())


def _texto(valor, largo: int) -> str:
	return _ascii(valor)[:largo].ljust(largo)


def _monto(valor) -> str:
	"""9999999999999.99: 16 posiciones con ceros a la izquierda y dos decimales."""
	return f"{max(flt(valor, 2), 0):016.2f}"


def _sexo(genero: str | None) -> str:
	inicial = _ascii(genero)[:1]
	return inicial if inicial in ("M", "F") else " "


def periodo(anio, mes) -> tuple[date, date]:
	anio, mes = cint(anio), cint(mes)
	return date(anio, mes, 1), date(anio, mes, monthrange(anio, mes)[1])


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------


def documento(emp) -> tuple[str | None, str, list[str]]:
	"""(tipo TSS, número, avisos) del trabajador."""
	avisos = []
	cedula = limpiar_identificacion(emp.rd_cedula)
	nss = limpiar_identificacion(emp.rd_nss)
	pasaporte = re.sub(r"[^A-Z0-9]", "", _ascii(emp.passport_number or emp.rd_numero_documento))

	if cedula:
		if not cedula_valida(cedula):
			avisos.append(_("La cédula {0} no parece válida").format(cedula))
		return TIPO_CEDULA, cedula, avisos
	if nss:
		return TIPO_NSS, nss, avisos
	if pasaporte and emp.rd_tipo_documento != "Otro":
		avisos.append(_("Extranjero con pasaporte: si la TSS ya le asignó NSS, regístrelo en la ficha"))
		return TIPO_PASAPORTE, pasaporte, avisos
	if emp.rd_tipo_documento == "Otro":
		avisos.append(
			_(
				"Sin NSS: la TSS no recibe ese documento. Solicite el NSS en el SUIR (Solicitud de asignación de NSS)"
			)
		)
	else:
		avisos.append(_("Sin cédula, NSS ni pasaporte en la ficha del empleado"))
	return None, "", avisos


def _empleados(company: str, desde: date, hasta: date, con_recibo: set[str]) -> list[frappe._dict]:
	"""Trabajadores en la nómina del mes: los activos en alguna fecha del período y los que tienen recibo."""
	campos = [
		"name",
		"employee_name",
		"first_name",
		"middle_name",
		"last_name",
		"rd_segundo_apellido",
		"gender",
		"date_of_birth",
		"date_of_joining",
		"relieving_date",
		"rd_tipo_documento",
		"rd_cedula",
		"rd_nss",
		"rd_numero_documento",
		"passport_number",
		"rd_clave_nomina",
		"rd_tipo_ingreso_tss",
	]
	empleados = frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ("<=", hasta)},
		fields=campos,
		order_by="employee_name",
	)
	return [
		e
		for e in empleados
		if e.name in con_recibo or not e.relieving_date or getdate(e.relieving_date) >= desde
	]


def _recibos(company: str, desde: date, hasta: date) -> dict[str, frappe._dict]:
	"""Salarios y retenciones de ley del mes por empleado según los recibos aprobados."""
	recibos = frappe.get_all(
		"Salary Slip",
		filters={"company": company, "docstatus": 1, "end_date": ("between", (desde, hasta))},
		fields=["name", "employee"],
	)
	totales = {}
	if not recibos:
		return totales
	empleado_de = {r.name: r.employee for r in recibos}
	filas = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Slip",
			"parentfield": ("in", ("earnings", "deductions")),
			"parent": ("in", list(empleado_de)),
		},
		fields=[
			"parent",
			"parentfield",
			"salary_component",
			"amount",
			"is_tax_applicable",
			"statistical_component",
			"do_not_include_in_total",
			"additional_salary",
		],
	)
	adicionales = {f.additional_salary for f in filas if f.additional_salary}
	de_prestaciones = set(
		frappe.get_all(
			"Additional Salary",
			filters={"name": ("in", list(adicionales)), "ref_doctype": "Gratuity"},
			pluck="name",
		)
		if adicionales
		else []
	)
	for r in recibos:
		totales.setdefault(
			r.employee, frappe._dict(salario_ss=0.0, salario_isr=0.0, otras=0.0, afp=0.0, sfs=0.0, isr=0.0)
		)
	retenciones = {salario.AFP: "afp", salario.SFS: "sfs", salario.ISR: "isr"}
	for f in filas:
		if f.parentfield == "deductions":
			clave = retenciones.get(salario._concepto(f.salary_component))
			if clave:
				totales[empleado_de[f.parent]][clave] += flt(f.amount)
			continue
		if cint(f.statistical_component) or cint(f.do_not_include_in_total):
			continue
		if f.additional_salary in de_prestaciones:
			continue  # va en los ingresos exentos
		t = totales[empleado_de[f.parent]]
		cotiza = cint(frappe.get_cached_value("Salary Component", f.salary_component, "rd_cotiza_tss"))
		if cotiza:
			t.salario_ss += flt(f.amount)
		if cint(f.is_tax_applicable):
			if cotiza:
				t.salario_isr += flt(f.amount)
			else:
				t.otras += flt(f.amount)
	return totales


def _exentos(company: str, desde: date, hasta: date) -> dict[str, dict[str, float]]:
	"""Regalía y preaviso / cesantía del mes (Gratuity con regla RD), por empleado y código."""
	exentos = {}
	if not frappe.get_meta("Gratuity Rule").has_field("rd_prestacion"):
		return exentos
	for g in frappe.get_all(
		"Gratuity",
		filters={"company": company, "docstatus": 1},
		fields=["employee", "amount", "gratuity_rule", "posting_date", "pay_via_salary_slip", "payroll_date"],
	):
		fecha = getdate(g.payroll_date if cint(g.pay_via_salary_slip) and g.payroll_date else g.posting_date)
		codigo = EXENTOS_POR_PRESTACION.get(
			frappe.get_cached_value("Gratuity Rule", g.gratuity_rule, "rd_prestacion")
		)
		if codigo and desde <= fecha <= hasta:
			por_codigo = exentos.setdefault(g.employee, {})
			por_codigo[codigo] = por_codigo.get(codigo, 0.0) + flt(g.amount)
	return exentos


def _tipo_ingreso(emp, desde: date, hasta: date) -> str:
	if emp.rd_tipo_ingreso_tss:
		return emp.rd_tipo_ingreso_tss[:4]
	entra = getdate(emp.date_of_joining) > desde
	sale = emp.relieving_date and getdate(emp.relieving_date) < hasta
	return MES_INCOMPLETO if entra or sale else NORMAL


def obtener(company: str, anio, mes) -> list[dict]:
	"""Una fila por trabajador del mes, con lo que va al archivo y las observaciones."""
	if not hrms_instalado():
		frappe.throw(_("El archivo de la TSS usa los recibos de nómina de Frappe HR, que no está instalado."))
	desde, hasta = periodo(anio, mes)
	salarios = _recibos(company, desde, hasta)
	exentos = _exentos(company, desde, hasta)

	filas = []
	for emp in _empleados(company, desde, hasta, set(salarios)):
		tipo, numero, avisos = documento(emp)
		s = salarios.get(emp.name)
		if not s:
			avisos.insert(0, _(SIN_RECIBO))
		clave = (emp.rd_clave_nomina or "001").strip().zfill(3)
		if not re.fullmatch(r"\d{3}", clave):
			avisos.append(_("La clave de nómina debe tener 3 dígitos"))
		if tipo in (TIPO_NSS, TIPO_PASAPORTE) and not (emp.last_name and emp.gender and emp.date_of_birth):
			avisos.append(_("Sin cédula, la TSS pide apellido, sexo y fecha de nacimiento"))
		e = exentos.get(emp.name, {})
		filas.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"clave_nomina": clave,
				"tipo_documento": tipo or "",
				"documento": numero,
				"nombres": " ".join(n for n in (emp.first_name, emp.middle_name) if n),
				"primer_apellido": emp.last_name or "",
				"segundo_apellido": emp.rd_segundo_apellido or "",
				"sexo": _sexo(emp.gender).strip(),
				"fecha_nacimiento": emp.date_of_birth,
				"salario_ss": flt(s.salario_ss, 2) if s else 0.0,
				"salario_isr": flt(s.salario_isr, 2) if s else 0.0,
				"otras_remuneraciones": flt(s.otras, 2) if s else 0.0,
				"afp": flt(s.afp, 2) if s else 0.0,
				"sfs": flt(s.sfs, 2) if s else 0.0,
				"isr_retenido": flt(s.isr, 2) if s else 0.0,
				"con_recibo": 1 if s else 0,
				"tipo_ingreso": _tipo_ingreso(emp, desde, hasta),
				"regalia": flt(e.get(REGALIA), 2),
				"prestaciones": flt(e.get(PRESTACIONES), 2),
				"_en_txt": 1 if s and tipo and re.fullmatch(r"\d{3}", clave) else 0,
				"_avisos": "; ".join(avisos),
			}
		)
	return filas


# ---------------------------------------------------------------------------
# Archivo
# ---------------------------------------------------------------------------


def linea_detalle(f: dict) -> str:
	nacimiento = getdate(f["fecha_nacimiento"]).strftime("%d%m%Y") if f.get("fecha_nacimiento") else " " * 8
	salario_isr = f["salario_isr"] if flt(f["salario_isr"], 2) != flt(f["salario_ss"], 2) else 0
	linea = "".join(
		[
			"D",
			f["clave_nomina"],
			f["tipo_documento"],
			_texto(f["documento"], 25),
			_texto(f["nombres"], 50),
			_texto(f["primer_apellido"], 40),
			_texto(f["segundo_apellido"], 40),
			_sexo(f.get("sexo")),
			nacimiento,
			_monto(f["salario_ss"]),
			_monto(0),  # aporte ordinario voluntario
			_monto(salario_isr),
			_monto(f["otras_remuneraciones"]),
			" " * 11,  # RNC del agente de retención único
			_monto(0),  # remuneraciones de otros empleadores
			_monto(0),  # ingresos exentos: se detallan al final
			_monto(0),  # saldo a favor
			_monto(0),  # salario INFOTEP: igual al de la TSS
			f["tipo_ingreso"],
		]
	)
	linea += _exentos_al_final(f)
	if len(linea) not in (LONGITUD_DETALLE, LONGITUD_CON_EXENTOS):
		frappe.throw(_("Registro de la TSS con longitud {0} para {1}").format(len(linea), f["employee"]))
	return linea


def _exentos_al_final(f: dict) -> str:
	"""Regalía (01), preaviso / cesantía (02) y pensión alimenticia (03), 18 posiciones cada uno, solo
	si hay alguno: el campo de ingresos exentos del registro queda en ceros."""
	if not (flt(f.get("regalia")) or flt(f.get("prestaciones"))):
		return ""
	return (
		REGALIA
		+ _monto(f.get("regalia"))
		+ PRESTACIONES
		+ _monto(f.get("prestaciones"))
		+ PENSION_ALIMENTICIA
		+ _monto(0)
	)


def linea_rectificativa(f: dict) -> str:
	"""Detalle de la rectificativa del IR-3 (RT): solo los datos del ISR, sin clave de nómina."""
	nacimiento = getdate(f["fecha_nacimiento"]).strftime("%d%m%Y") if f.get("fecha_nacimiento") else " " * 8
	linea = "".join(
		[
			"D",
			"P" if f.get("tipo_ingreso") == PENSIONADO else "N",  # tipo de trabajador
			f["tipo_documento"],
			_texto(f["documento"], 25),
			_texto(f["nombres"], 50),
			_texto(f["primer_apellido"], 40),
			_texto(f["segundo_apellido"], 40),
			_sexo(f.get("sexo")),
			nacimiento,
			_monto(f["salario_isr"]),  # en la rectificativa siempre se informa
			_monto(f["otras_remuneraciones"]),
			" " * 11,  # agente de retención
			_monto(0),  # remuneraciones de otros agentes
			_monto(0),  # ingresos exentos: se detallan al final
			_monto(0),  # saldo a favor
		]
	)
	linea += _exentos_al_final(f)
	if len(linea) not in (LONGITUD_RECTIFICATIVA, LONGITUD_RECTIFICATIVA + 54):
		frappe.throw(_("Registro de la TSS con longitud {0} para {1}").format(len(linea), f["employee"]))
	return linea


def rnc_de(company: str) -> str:
	if not es_empresa_rd(company):
		frappe.throw(_("El archivo de la TSS es solo para empresas de República Dominicana."))
	rnc = rnc_empresa(company)
	if not rnc:
		frappe.throw(_("La empresa {0} no tiene RNC (ID Fiscal)").format(company))
	return rnc


def armar_archivo(rnc: str, proceso: str, anio, mes, detalles: list[str]) -> tuple[str, str]:
	"""(nombre, contenido): encabezado, detalles y sumario (registros contando E y S), en CRLF."""
	mes_anio = f"{cint(mes):02d}{cint(anio):04d}"
	# La rectificativa lleva el proceso en 4 posiciones (relleno de espacios a la derecha)
	codigo = proceso.ljust(4) if proceso == RECTIFICATIVA else proceso
	lineas = ["E" + codigo + rnc.rjust(11) + mes_anio, *detalles]
	lineas.append("S" + str(len(lineas) + 1).zfill(6))
	return f"{proceso}_{rnc}_{mes_anio}.txt", "\r\n".join(lineas) + "\r\n"


def generar_txt(company: str, anio, mes, proceso: str = PROCESO) -> tuple[str, str]:
	"""Devuelve (nombre de archivo, contenido) del archivo AM o de la rectificativa del IR-3 (RT)."""
	rnc = rnc_de(company)
	filas = [f for f in obtener(company, anio, mes) if f["_en_txt"]]
	if not filas:
		frappe.throw(
			_("No hay trabajadores con recibo de nómina aprobado y documento en este período."),
			title=_("Sin registros"),
		)
	linea = linea_rectificativa if proceso == RECTIFICATIVA else linea_detalle
	return armar_archivo(rnc, proceso, anio, mes, [linea(f) for f in filas])


def responder_archivo(nombre: str, contenido: str):
	frappe.response["filename"] = nombre
	frappe.response["filecontent"] = contenido.encode("ascii")
	frappe.response["type"] = "download"


@frappe.whitelist()
def descargar_txt(company: str, anio: int, mes: int, proceso: str = PROCESO):
	frappe.only_for(ROLES)
	frappe.has_permission("Company", doc=company, throw=True)
	if proceso not in (PROCESO, RECTIFICATIVA):
		frappe.throw(_("Proceso de la TSS no válido: {0}").format(proceso))
	responder_archivo(*generar_txt(company, anio, mes, proceso))


# ---------------------------------------------------------------------------
# Script Report
# ---------------------------------------------------------------------------


def _columnas() -> list[dict]:
	def col(fieldname, label, fieldtype="Data", width=110, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("employee", "Empleado", "Link", 130, options="Employee"),
		col("employee_name", "Nombre", width=200),
		col("clave_nomina", "Nómina", width=70),
		col("tipo_documento", "Tipo doc.", width=70),
		col("documento", "Documento", width=120),
		col("salario_ss", "Salario SS", "Currency", 120),
		col("salario_isr", "Salario ISR", "Currency", 120),
		col("otras_remuneraciones", "Otras remuneraciones ISR", "Currency", 140),
		col("regalia", "Regalía (exenta)", "Currency", 120),
		col("prestaciones", "Preaviso y cesantía (exentos)", "Currency", 150),
		col("tipo_ingreso", "Tipo de ingreso", width=90),
		col("_en_txt", "En el archivo", "Check", 80),
		col("_avisos", "Observaciones", width=360),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio and filters.mes):
		return _columnas(), []
	filas = obtener(filters.company, filters.anio, filters.mes)
	en_txt = [f for f in filas if f["_en_txt"]]
	con_avisos = sum(1 for f in filas if f["_avisos"])
	resumen = [
		{
			"label": _("Trabajadores en el archivo"),
			"value": len(en_txt),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"label": _("Con observaciones"),
			"value": con_avisos,
			"datatype": "Int",
			"indicator": "Orange" if con_avisos else "Green",
		},
		{
			"label": _("Salario SS"),
			"value": sum(f["salario_ss"] for f in en_txt),
			"datatype": "Currency",
			"indicator": "Blue",
		},
	]
	return _columnas(), filas, None, None, resumen
