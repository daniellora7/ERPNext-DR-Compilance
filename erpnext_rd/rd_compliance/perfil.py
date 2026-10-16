"""Perfil tributario de cada empresa de RD (Fase 8 del plan).

El *Perfil Tributario RD* dice bajo qué régimen opera la empresa, su tamaño, su cierre fiscal, qué
actividades con tratamiento especial realiza, qué incentivos tiene y su situación con el e-CF. Todo lo
que dependa de eso pregunta aquí en vez de suponer el régimen ordinario. Sin perfil, la empresa se
trata como persona jurídica del régimen ordinario con cierre al 31 de diciembre (lo de siempre).

Requisitos: cada regla registrada con `@requisito` dice, para un perfil, qué tiene que estar
configurado y si lo está. La pantalla del perfil y el aviso de la empresa los muestran; los módulos
de cada régimen agregan sus propias reglas. Estados:
- Cumplido / Falta: la app lo puede revisar.
- Pendiente en la app: la empresa lo tiene pero la app aún no lo cubre (siguientes ramas de la Fase 8).
- Fuera del alcance: sectores regulados.
"""

from dataclasses import dataclass
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_years, cint, getdate, today

DOCTYPE = "Perfil Tributario RD"

JURIDICA = "Persona jurídica"
FISICA = "Persona física con negocio"
ORDINARIO = "Ordinario"
RST = "Simplificado (RST)"
CIERRES = {
	"31 de diciembre": (12, 31),
	"31 de marzo": (3, 31),
	"30 de junio": (6, 30),
	"30 de septiembre": (9, 30),
}
CIERRE_POR_DEFECTO = "31 de diciembre"
# Ley 488-08 (mipymes), modificada por la Ley 187-17: trabajadores y ventas brutas anuales
MICRO = "Micro (hasta 10 empleados)"
PEQUENA = "Pequeña (11 a 50 empleados)"
MEDIANA = "Mediana (51 a 150 empleados)"
GRANDE = "Grande (más de 150 empleados)"
TAMANOS = (MICRO, PEQUENA, MEDIANA, GRANDE)
SIN_SECTOR_REGULADO = "No aplica"
ECF_NO_OBLIGADA = "No obligada aún"
ECF_CERTIFICACION = "En certificación"
ECF_EMISOR = "Emisor electrónico"
CAMPOS_ISC = ("isc_alcohol", "isc_tabaco", "isc_combustibles", "isc_telecomunicaciones", "isc_seguros")
ACTIVIDADES = (*CAMPOS_ISC, "propina_legal", "partes_relacionadas", "exportador", "agente_retencion")

CUMPLIDO = "Cumplido"
FALTA = "Falta"
PENDIENTE_APP = "Pendiente en la app"
FUERA_ALCANCE = "Fuera del alcance"


# ---------------------------------------------------------------------- perfil


def perfil(company: str) -> frappe._dict:
	"""El perfil de la empresa o, si no tiene, el del régimen ordinario (con `existe` = False)."""
	if company and frappe.db.exists(DOCTYPE, company):
		doc = frappe.get_cached_doc(DOCTYPE, company)
		datos = frappe._dict(doc.as_dict())
		datos.existe = True
		return datos
	return frappe._dict(
		company=company,
		tipo_contribuyente=JURIDICA,
		regimen=ORDINARIO,
		tamano=None,
		cierre_fiscal=CIERRE_POR_DEFECTO,
		ecf_estado=ECF_NO_OBLIGADA,
		ecf_obligada_desde=None,
		sector_regulado=SIN_SECTOR_REGULADO,
		incentivos=[],
		existe=False,
		**{c: 0 for c in ACTIVIDADES},
	)


def declara_ir2(company: str) -> bool:
	"""Persona jurídica del régimen ordinario: IR-2, su cuadre, anexos y anticipos de sociedades."""
	p = perfil(company)
	return p.tipo_contribuyente == JURIDICA and p.regimen == ORDINARIO


def emisor_electronico(company: str) -> bool:
	return perfil(company).ecf_estado == ECF_EMISOR


def cierre(company: str) -> tuple[int, int]:
	"""(mes, día) del cierre fiscal de la empresa."""
	return CIERRES.get(perfil(company).cierre_fiscal, CIERRES[CIERRE_POR_DEFECTO])


def incentivos_vigentes(company: str, fecha=None) -> list[frappe._dict]:
	fecha = getdate(fecha or today())
	return [
		i
		for i in perfil(company).incentivos
		if (not i.desde or getdate(i.desde) <= fecha) and (not i.hasta or getdate(i.hasta) >= fecha)
	]


def anio_fiscal(company: str, fecha) -> frappe._dict | None:
	"""Año fiscal de ERPNext que cubre `fecha` para la empresa (el suyo o uno para todas)."""
	filas = frappe.db.sql(
		"""SELECT fy.name, fy.year_start_date AS desde, fy.year_end_date AS hasta FROM `tabFiscal Year` fy
		WHERE fy.disabled = 0 AND %(fecha)s BETWEEN fy.year_start_date AND fy.year_end_date
			AND (
				NOT EXISTS (SELECT 1 FROM `tabFiscal Year Company` c WHERE c.parent = fy.name)
				OR EXISTS (
					SELECT 1 FROM `tabFiscal Year Company` c WHERE c.parent = fy.name AND c.company = %(company)s
				)
			)
		ORDER BY (SELECT COUNT(*) FROM `tabFiscal Year Company` c WHERE c.parent = fy.name) DESC""",
		{"fecha": getdate(fecha), "company": company},
		as_dict=True,
	)
	return filas[0] if filas else None


def periodo_fiscal(company: str, fecha=None) -> tuple[date, date]:
	"""Inicio y cierre del ejercicio que contiene `fecha` según el cierre del perfil."""
	fecha = getdate(fecha or today())
	mes, dia = cierre(company)
	fin = date(fecha.year, mes, dia)
	if fin < fecha:
		fin = date(fecha.year + 1, mes, dia)
	return add_days(add_years(fin, -1), 1), fin


# ---------------------------------------------------------------------- requisitos


@dataclass
class Requisito:
	nombre: str
	verificar: object  # (company, perfil) -> dict | None (None: no aplica)
	obligatorio: bool = False


REQUISITOS: list[Requisito] = []


def requisito(nombre: str, obligatorio: bool = False):
	"""Registra una regla. La función recibe (company, perfil) y devuelve None si no aplica o un
	dict con `estado` y opcionalmente `detalle` y `ruta` (argumentos de frappe.set_route)."""

	def registrar(funcion):
		REQUISITOS.append(Requisito(nombre, funcion, obligatorio))
		return funcion

	return registrar


def _resultado(ok: bool, detalle: str = "", ruta=None) -> dict:
	return {"estado": CUMPLIDO if ok else FALTA, "detalle": detalle, "ruta": ruta}


def evaluar(company: str) -> list[dict]:
	"""Requisitos de las reglas registradas y lo que la app aún no cubre."""
	p = perfil(company)
	return _reglas(company, p) + pendientes(company, p)


def _reglas(company: str, p) -> list[dict]:
	lista = []
	for r in REQUISITOS:
		resultado = r.verificar(company, p)
		if resultado:
			lista.append({"requisito": _(r.nombre), "obligatorio": r.obligatorio, **resultado})
	return lista


@frappe.whitelist()
def requisitos(company: str) -> list[dict]:
	frappe.has_permission("Company", "read", company, throw=True)
	return evaluar(company)


@frappe.whitelist()
def estado_empresa(company: str) -> dict:
	"""Para el aviso de la empresa: si tiene perfil y cuántos requisitos obligatorios faltan."""
	frappe.has_permission("Company", "read", company, throw=True)
	from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd

	if not es_empresa_rd(company):
		return {"aplica": False}
	faltan = [r for r in evaluar(company) if r["obligatorio"] and r["estado"] == FALTA]
	return {"aplica": True, "existe": bool(frappe.db.exists(DOCTYPE, company)), "faltan": len(faltan)}


@frappe.whitelist()
def guardar(company: str, valores: str | dict) -> str:
	"""Asistente: crea o actualiza el perfil con los datos de sus pasos."""
	valores = frappe.parse_json(valores) if isinstance(valores, str) else valores
	permitidos = {
		"tipo_contribuyente",
		"regimen",
		"tamano",
		"cierre_fiscal",
		"sector_regulado",
		"ecf_estado",
		"ecf_obligada_desde",
		*ACTIVIDADES,
	}
	datos = {k: v for k, v in (valores or {}).items() if k in permitidos}
	if frappe.db.exists(DOCTYPE, company):
		doc = frappe.get_doc(DOCTYPE, company)
		doc.update(datos)
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": DOCTYPE, "company": company, **datos}).insert()
	return doc.name


@frappe.whitelist()
def crear_anio_fiscal(company: str) -> str:
	"""Crea el año fiscal de ERPNext del ejercicio en curso según el cierre del perfil."""
	frappe.has_permission("Fiscal Year", "create", throw=True)
	actual = anio_fiscal(company, today())
	if actual:
		return actual.name
	desde, hasta = periodo_fiscal(company)
	nombre = str(hasta.year) if desde.year == hasta.year else f"{desde.year}-{hasta.year}"
	if frappe.db.exists("Fiscal Year", nombre):
		nombre = f"{nombre} {frappe.get_cached_value('Company', company, 'abbr')}"
	return (
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": nombre,
				"year_start_date": desde,
				"year_end_date": hasta,
				"companies": [{"company": company}],
			}
		)
		.insert()
		.name
	)


# ---------------------------------------------------------------------- reglas del núcleo


@requisito("Perfil tributario completo", obligatorio=True)
def _perfil_completo(company, p):
	if not p.existe:
		return _resultado(False, _("La empresa no tiene perfil tributario."), ["Form", DOCTYPE, "new"])
	if not p.tamano:
		return _resultado(False, _("Indique el tamaño de la empresa."), ["Form", DOCTYPE, company])
	return _resultado(True)


@requisito("RNC de la empresa", obligatorio=True)
def _rnc(company, p):
	from erpnext_rd.dgii_fiscal.identificacion import identificacion_valida

	rnc = frappe.get_cached_value("Company", company, "tax_id")
	return _resultado(
		identificacion_valida(rnc),
		"" if rnc else _("Escriba el RNC (o la cédula) en «Tax ID» de la empresa."),
		["Form", "Company", company],
	)


@requisito("Año fiscal según el cierre", obligatorio=True)
def _anio_fiscal(company, p):
	actual = anio_fiscal(company, today())
	mes, dia = cierre(company)
	if not actual:
		return _resultado(
			False,
			_("No hay año fiscal de ERPNext para hoy. Use «Crear año fiscal»."),
			["List", "Fiscal Year"],
		)
	fin = getdate(actual.hasta)
	if (fin.month, fin.day) != (mes, dia):
		return _resultado(
			False,
			_("El año fiscal {0} cierra el {1}, pero el perfil dice {2}.").format(
				actual.name, frappe.format(fin, "Date"), p.cierre_fiscal
			),
			["Form", "Fiscal Year", actual.name],
		)
	return _resultado(True, actual.name)


def tipos_de_venta(company: str) -> list[str]:
	"""Comprobantes que la empresa necesita para vender según su perfil."""
	p = perfil(company)
	serie_e = p.ecf_estado == ECF_EMISOR
	tipos = ["E31", "E32", "E34"] if serie_e else ["B01", "B02", "B04"]
	if p.exportador:
		tipos.append("E46" if serie_e else "B16")
	return tipos


def secuencia_vigente(company: str, tipo: str) -> bool:
	return bool(
		frappe.db.sql(
			"""SELECT name FROM `tabSecuencia NCF`
			WHERE company = %(company)s AND tipo_comprobante = %(tipo)s AND habilitada = 1
				AND siguiente <= hasta AND (fecha_vencimiento IS NULL OR fecha_vencimiento >= %(hoy)s)
			LIMIT 1""",
			{"company": company, "tipo": tipo, "hoy": today()},
		)
	)


@requisito("Secuencias NCF de venta vigentes", obligatorio=True)
def _secuencias(company, p):
	faltan = [t for t in tipos_de_venta(company) if not secuencia_vigente(company, t)]
	return _resultado(
		not faltan,
		_("Sin secuencia vigente: {0}").format(", ".join(faltan))
		if faltan
		else ", ".join(tipos_de_venta(company)),
		["List", "Secuencia NCF", {"company": company}],
	)


@requisito("Emisor e-CF con certificado vigente", obligatorio=True)
def _emisor_ecf(company, p):
	if p.ecf_estado == ECF_NO_OBLIGADA:
		return None
	emisor = frappe.db.get_value(
		"Emisor ECF", company, ["habilitado", "certificado", "vigente_hasta"], as_dict=True
	)
	if not emisor or not emisor.certificado:
		return _resultado(
			False, _("Registre el emisor con su certificado .p12."), ["Form", "Emisor ECF", company]
		)
	if emisor.vigente_hasta and getdate(emisor.vigente_hasta) < getdate(today()):
		return _resultado(False, _("El certificado está vencido."), ["Form", "Emisor ECF", company])
	return _resultado(
		bool(emisor.habilitado),
		"" if emisor.habilitado else _("El emisor está deshabilitado."),
		["Form", "Emisor ECF", company],
	)


@requisito("Facturación electrónica a tiempo", obligatorio=True)
def _ecf_a_tiempo(company, p):
	if not p.ecf_obligada_desde or p.ecf_estado == ECF_EMISOR:
		return None
	fecha = getdate(p.ecf_obligada_desde)
	return _resultado(
		fecha > getdate(today()),
		_("Obligada a emitir e-CF desde el {0}.").format(frappe.format(fecha, "Date")),
		["Form", DOCTYPE, company],
	)


@requisito("Plantilla de propina legal")
def _propina(company, p):
	if not p.propina_legal:
		return None
	from erpnext_rd.dgii_fiscal.catalogos import PROPINA_LEGAL

	existe = frappe.db.sql(
		"""SELECT t.name FROM `tabSales Taxes and Charges Template` t
		JOIN `tabSales Taxes and Charges` c ON c.parent = t.name
		JOIN `tabAccount` a ON a.name = c.account_head
		WHERE t.company = %s AND t.disabled = 0 AND a.rd_concepto_fiscal = %s LIMIT 1""",
		(company, PROPINA_LEGAL),
	)
	return _resultado(
		bool(existe),
		"" if existe else _("Cree una plantilla de impuestos de venta con la cuenta de propina legal."),
		["List", "Sales Taxes and Charges Template", {"company": company}],
	)


@requisito("Casillas del IR-2 en el catálogo de cuentas")
def _casillas_ir2(company, p):
	if not declara_ir2(company):
		return None
	from erpnext_rd.dgii_reportes import estados_ir2

	_casillas, por_tipo = estados_ir2.casillas_de_cuentas(company)
	return _resultado(
		not por_tipo,
		_("{0} cuentas sin casilla (se clasifican por su tipo).").format(len(por_tipo)) if por_tipo else "",
		["Tree", "Account"],
	)


@requisito("Categoría fiscal en las categorías de activo")
def _categorias_activo(company, p):
	if not declara_ir2(company):
		return None
	usadas = frappe.get_all(
		"Asset", filters={"company": company, "docstatus": 1}, pluck="asset_category", distinct=True
	)
	if not usadas:
		return None
	sin = [c for c in usadas if not frappe.get_cached_value("Asset Category", c, "rd_categoria_fiscal")]
	return _resultado(not sin, ", ".join(sin), ["List", "Asset Category"])


@requisito("Multiplicador de inflación del último cierre")
def _multiplicador(company, p):
	if not declara_ir2(company):
		return None
	from erpnext_rd.dgii_reportes import ir2

	desde, _hasta = periodo_fiscal(company)
	ultimo = add_days(desde, -1)
	return _resultado(
		bool(ir2.multiplicador(ultimo)),
		_("Cierre del {0}").format(frappe.format(ultimo, "Date")),
		["Form", "Configuracion DGII"],
	)


# Lo que la empresa tiene pero la app aún no cubre (siguientes ramas de la Fase 8)
PENDIENTES = (
	(lambda p: any(cint(p.get(c)) for c in CAMPOS_ISC), "Impuesto selectivo al consumo (ISC)", "8.2"),
	(lambda p: cint(p.partes_relacionadas), "Operaciones con partes relacionadas (DIOR)", "8.3"),
	(lambda p: cint(p.exportador), "Reembolso o compensación del ITBIS de exportadores", "8.4"),
	(lambda p: bool(p.incentivos), "Regímenes especiales e incentivos", "8.4 y 8.6"),
	(lambda p: p.regimen == RST, "Régimen simplificado de tributación (RST)", "8.7"),
	(lambda p: p.tipo_contribuyente == FISICA, "Persona física con negocio (IR-1)", "8.8"),
)


def pendientes(company: str, p) -> list[dict]:
	filas = [
		{
			"requisito": _(nombre),
			"obligatorio": False,
			"estado": PENDIENTE_APP,
			"detalle": _("La app aún no lo cubre (plan, Fase {0}): llévelo aparte.").format(fase),
			"ruta": None,
		}
		for condicion, nombre, fase in PENDIENTES
		if condicion(p)
	]
	if p.sector_regulado and p.sector_regulado != SIN_SECTOR_REGULADO:
		filas.append(
			{
				"requisito": _("Reportes del sector regulado ({0})").format(_(p.sector_regulado)),
				"obligatorio": False,
				"estado": FUERA_ALCANCE,
				"detalle": _("Los reportes a la superintendencia no están en la app."),
				"ruta": None,
			}
		)
	return filas


# ---------------------------------------------------------------------- exigencia


def validar_serie_de_venta(doc, tipo):
	"""Un emisor electrónico vende con comprobantes electrónicos. Las notas de crédito y débito de
	facturas con NCF de serie B (de antes de ser emisor) siguen en la serie B."""
	if tipo.serie != "B" or doc.is_return or doc.get("is_debit_note"):
		return
	if emisor_electronico(doc.company):
		frappe.throw(
			_(
				"{0} es emisor electrónico según su perfil tributario: use el comprobante electrónico "
				"(serie E) en lugar de {1}."
			).format(doc.company, tipo.name),
			title=_("Comprobante no permitido"),
		)
