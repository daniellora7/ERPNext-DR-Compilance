"""Planillas del Ministerio de Trabajo para el SIRLA: personal fijo (DGT-3) y sus cambios (DGT-4).

Formato: «Especificaciones del archivo para la carga de trabajadores» DGT-3 y DGT-4 del SIRLA
(ovi.mt.gob.do → layoutsArchivoDGT). Texto de ancho fijo con encabezado (E + T3/T4 + RNC + MMAAAA),
un detalle por trabajador y sumario (S + registros con E y S). Alfanuméricos a la izquierda con
espacios; numéricos a la derecha con ceros.

Las dos tablas oficiales se contradicen en las posiciones finales: el DGT-3 deja sin describir las
posiciones 378-388 y el DGT-4 encima la fecha del cambio con el nivel educativo. Leídas juntas, el
detalle del DGT-3 es el del DGT-4 sin la fecha de salida: nacionalidad (3) y fecha del cambio (8) van
entre la localidad y el nivel educativo (443 posiciones en el DGT-3, 451 en el DGT-4).

- DGT-3 (a más tardar el 15 de enero, art. 15 del Reglamento 258-93): todos los trabajadores fijos
  activos, novedad NI.
- DGT-4 (cambios del mes): ingresos NI, salidas NS y cambios de salario NC, de los mismos eventos que el
  archivo de novedades de la TSS (`novedades._eventos`).

Los códigos de los catálogos del SIRLA (ocupación, turno, localidad del RNL, nivel educativo,
discapacidad, nacionalidad) van en la ficha del empleado; la localidad, por defecto, en la empresa.
"""

import re
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext_rd.nomina_rd import novedades, prestaciones, tss

DGT3 = "T3"
DGT4 = "T4"
INGRESO = "NI"
SALIDA = "NS"
CAMBIO = "NC"
EVENTOS = {novedades.INGRESO: INGRESO, novedades.SALIDA: SALIDA, novedades.ACTUALIZACION: CAMBIO}
LONGITUDES = {DGT3: 443, DGT4: 451}
# Además de los de la TSS, el SIRLA recibe el carné de migración (M)
MIGRACION = "M"

CAMPOS = [
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
	"designation",
	"rd_tipo_documento",
	"rd_cedula",
	"rd_nss",
	"rd_numero_documento",
	"passport_number",
	"rd_ocupacion_sirla",
	"rd_turno_sirla",
	"rd_localidad_sirla",
	"rd_nivel_educativo_sirla",
	"rd_discapacidad_sirla",
	"rd_nacionalidad_sirla",
]


def _alfa(valor, largo: int) -> str:
	return tss._texto(valor, largo)


def _num(valor, largo: int) -> str:
	digitos = re.sub(r"\D", "", str(valor or ""))
	return digitos[-largo:].rjust(largo, "0")


def _fecha(valor) -> str:
	return getdate(valor).strftime("%d%m%Y") if valor else "0" * 8


def documento(emp) -> tuple[str | None, str, list[str]]:
	tipo, numero, avisos = tss.documento(emp)
	if not tipo and emp.rd_tipo_documento == "Otro" and emp.rd_numero_documento:
		# Para el Ministerio de Trabajo vale el carné de migración (la TSS no lo recibe)
		return (
			MIGRACION,
			re.sub(r"[^A-Z0-9]", "", tss._ascii(emp.rd_numero_documento)),
			[_("Se envía como carné de migración")],
		)
	return tipo, numero, avisos


def _vacaciones(empleado: str, anio: int) -> tuple:
	"""Primeras vacaciones aprobadas del año (tipo de permiso de vacaciones RD)."""
	from erpnext_rd.nomina_rd import vacaciones

	tipo = vacaciones.tipo_vacaciones() if frappe.db.exists("DocType", "Leave Application") else None
	if not tipo:
		return None, None
	permiso = frappe.get_all(
		"Leave Application",
		filters={
			"employee": empleado,
			"leave_type": tipo,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ("between", (date(anio, 1, 1), date(anio, 12, 31))),
		},
		fields=["from_date", "to_date"],
		order_by="from_date",
		limit=1,
	)
	return (permiso[0].from_date, permiso[0].to_date) if permiso else (None, None)


def fila(emp, novedad: str, fecha_referencia, localidad_empresa: str, fecha_cambio=None) -> dict:
	"""Datos de un trabajador para el DGT-3 / DGT-4, con sus observaciones."""
	tipo, numero, avisos = documento(emp)
	salario = prestaciones.base_asignada(emp.name, fecha_referencia)
	inicio_vac, fin_vac = _vacaciones(emp.name, getdate(fecha_referencia).year)
	localidad = emp.rd_localidad_sirla or localidad_empresa
	faltan = [
		etiqueta
		for etiqueta, valor in (
			(_("ocupación"), emp.rd_ocupacion_sirla),
			(_("turno"), emp.rd_turno_sirla),
			(_("localidad"), localidad),
			(_("nivel educativo"), emp.rd_nivel_educativo_sirla),
			(_("cargo"), emp.designation),
		)
		if not valor
	]
	if faltan:
		avisos.append(_("Faltan códigos del SIRLA: {0}").format(", ".join(faltan)))
	if not salario:
		avisos.append(_("Sin asignación de estructura salarial: salario en cero"))
	if not inicio_vac:
		avisos.append(_("Sin vacaciones aprobadas en el año"))
	if tss._sexo(emp.gender) == " ":
		avisos.append(_("El SIRLA pide el sexo (M o F)"))
	return {
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"novedad": novedad,
		"tipo_documento": tipo or "",
		"documento": numero,
		"nombres": " ".join(n for n in (emp.first_name, emp.middle_name) if n),
		"primer_apellido": emp.last_name or "",
		"segundo_apellido": emp.rd_segundo_apellido or "",
		"fecha_nacimiento": emp.date_of_birth,
		"sexo": tss._sexo(emp.gender).strip(),
		"salario": flt(salario, 2),
		"fecha_ingreso": emp.date_of_joining,
		"fecha_salida": emp.relieving_date if novedad == SALIDA else None,
		"ocupacion": emp.rd_ocupacion_sirla or "",
		"cargo": emp.designation or "",
		"inicio_vacaciones": inicio_vac,
		"fin_vacaciones": fin_vac,
		"turno": emp.rd_turno_sirla or "",
		"localidad": localidad or "",
		"nacionalidad": emp.rd_nacionalidad_sirla or "",
		"fecha_cambio": fecha_cambio,
		"nivel_educativo": emp.rd_nivel_educativo_sirla or "",
		"discapacidad": emp.rd_discapacidad_sirla or "",
		"_en_txt": 1 if tipo else 0,
		"_avisos": "; ".join(avisos),
	}


def obtener(company: str, anio, mes, formulario: str = DGT3) -> list[dict]:
	from erpnext_rd.nomina_rd import hrms_instalado

	if not hrms_instalado():
		frappe.throw(_("Las planillas del SIRLA usan los salarios de Frappe HR, que no está instalado."))
	desde, hasta = tss.periodo(anio, mes)
	localidad = frappe.get_cached_value("Company", company, "rd_localidad_sirla") or ""
	empleados = {
		e.name: e
		for e in frappe.get_all(
			"Employee", filters={"company": company, "date_of_joining": ("<=", hasta)}, fields=CAMPOS
		)
	}
	filas = []
	if formulario == DGT3:
		for emp in sorted(empleados.values(), key=lambda e: e.employee_name or ""):
			if emp.relieving_date and getdate(emp.relieving_date) < desde:
				continue
			filas.append(fila(emp, INGRESO, hasta, localidad))
		return filas
	for ev in novedades._eventos(company, desde, hasta):
		novedad = EVENTOS.get(ev.tipo)
		if not novedad or ev.employee not in empleados:
			continue
		filas.append(
			fila(
				empleados[ev.employee],
				novedad,
				ev.inicio,
				localidad,
				fecha_cambio=ev.inicio if novedad == CAMBIO else None,
			)
		)
	return sorted(filas, key=lambda f: (f["novedad"], f["employee_name"] or ""))


def linea(f: dict, formulario: str) -> str:
	partes = [
		"D",
		_alfa(f["novedad"], 3),
		_alfa(f["tipo_documento"], 1),
		_alfa(f["documento"], 25),
		_alfa(f["nombres"], 50),
		_alfa(f["primer_apellido"], 40),
		_alfa(f["segundo_apellido"], 40),
		_fecha(f["fecha_nacimiento"]),
		_alfa(f["sexo"], 1),
		f"{max(flt(f['salario'], 2), 0):016.2f}",
		_fecha(f["fecha_ingreso"]),
	]
	if formulario == DGT4:
		partes.append(_fecha(f["fecha_salida"]))
	partes += [
		_num(f["ocupacion"], 6),
		_alfa(f["cargo"], 150),
		_fecha(f["inicio_vacaciones"]),
		_fecha(f["fin_vacaciones"]),
		_num(f["turno"], 6),
		_num(f["localidad"], 6),
		_alfa(f["nacionalidad"], 3),
		_fecha(f["fecha_cambio"]),
		_num(f["nivel_educativo"], 5),
		_alfa(f["discapacidad"], 50),
	]
	resultado = "".join(partes)
	if len(resultado) != LONGITUDES[formulario]:
		frappe.throw(_("Registro del SIRLA con longitud {0} para {1}").format(len(resultado), f["employee"]))
	return resultado


def generar_txt(company: str, anio, mes, formulario: str = DGT3) -> tuple[str, str]:
	if formulario not in LONGITUDES:
		frappe.throw(_("Formulario del SIRLA no válido: {0}").format(formulario))
	rnc = tss.rnc_de(company)
	filas = [f for f in obtener(company, anio, mes, formulario) if f["_en_txt"]]
	if not filas:
		frappe.throw(_("No hay trabajadores con documento para este formulario."), title=_("Sin registros"))
	mes_anio = f"{cint(mes):02d}{cint(anio):04d}"
	lineas = ["E" + formulario + _num(rnc, 11) + mes_anio, *[linea(f, formulario) for f in filas]]
	lineas.append("S" + str(len(lineas) + 1).zfill(6))
	nombre = f"DGT{formulario[1]}_{rnc}_{mes_anio}.txt"
	return nombre, "\r\n".join(lineas) + "\r\n"


@frappe.whitelist()
def descargar_txt(company: str, anio: int, mes: int, formulario: str = DGT3):
	frappe.only_for(tss.ROLES)
	frappe.has_permission("Company", doc=company, throw=True)
	tss.responder_archivo(*generar_txt(company, anio, mes, formulario))


# ---------------------------------------------------------------------------
# Script Report
# ---------------------------------------------------------------------------


def _columnas() -> list[dict]:
	def col(fieldname, label, fieldtype="Data", width=110, **extra):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("novedad", "Novedad", width=80),
		col("employee", "Empleado", "Link", 130, options="Employee"),
		col("employee_name", "Nombre", width=190),
		col("documento", "Documento", width=120),
		col("cargo", "Cargo", width=150),
		col("ocupacion", "Ocupación", width=90),
		col("salario", "Salario", "Currency", 120),
		col("fecha_ingreso", "Ingreso", "Date", 100),
		col("inicio_vacaciones", "Vacaciones", "Date", 100),
		col("_en_txt", "En el archivo", "Check", 80),
		col("_avisos", "Observaciones", width=360),
	]


def ejecutar_reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	if not (filters.company and filters.anio and filters.mes):
		return _columnas(), []
	formulario = filters.formulario or DGT3
	filas = obtener(filters.company, filters.anio, filters.mes, formulario)
	con_avisos = sum(1 for f in filas if f["_avisos"])
	resumen = [
		{
			"label": _("Trabajadores en el archivo"),
			"value": sum(f["_en_txt"] for f in filas),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"label": _("Con observaciones"),
			"value": con_avisos,
			"datatype": "Int",
			"indicator": "Orange" if con_avisos else "Green",
		},
	]
	if formulario == DGT3:
		mensaje = _(
			"Planilla del personal fijo (DGT-3): se presenta en el SIRLA a más tardar el 15 de enero de cada año "
			"(Oficina Virtual del Ministerio de Trabajo → Carga de trabajadores). Los códigos de ocupación, turno, "
			"localidad, nivel educativo y discapacidad son los de los catálogos del SIRLA."
		)
	else:
		mensaje = _(
			"Cambios a la planilla (DGT-4): ingresos, salidas y cambios de salario del mes. Se cargan en el SIRLA "
			"(Carga de trabajadores) o uno a uno en el formulario DGT-4."
		)
	return _columnas(), filas, mensaje, None, resumen
