"""Anticipos del ISR de las personas jurídicas (art. 314 del Código Tributario).

Cada año, con los datos de la declaración jurada (IR-2), se registra una *Base Anticipo ISR*:
- Tasa efectiva de tributación (TET) = impuesto liquidado / ingresos brutos.
- TET mayor que la tasa mínima (1.5%, editable en *Configuracion DGII*): el anticipo mensual es la
  doceava parte del impuesto liquidado.
- TET igual o menor: el anticipo es la tasa mínima sobre los ingresos brutos, en doce cuotas.

El anticipo de cada mes vence el día 15 del mes siguiente (o el siguiente día hábil). La base nueva
rige desde el mes siguiente a la fecha límite del IR-2: con cierre al 31 de diciembre, el primer
pago con la base nueva es el del 15 de mayo.

Ley 30-26 (art. 23, que modifica el art. 314), desde la base del ejercicio 2026 (anticipos de 2027,
calendario de implementación de la DGII):
- Medianas y grandes: igual que antes, mensual.
- Pequeñas y personas físicas (párrafo II): el 100% del impuesto liquidado en tres cuotas, en el sexto, noveno y
  duodécimo mes del ejercicio (50%, 30% y 20%, en *Configuracion DGII*). Cada cuota vence el último
  día de su mes: 30 de junio, 30 de septiembre y 31 de diciembre con cierre al 31 de diciembre
  (Guía del Contribuyente No. 12 de la DGII, julio de 2026).
- Microempresas (párrafo III): exentas.
El régimen se propone con el tamaño del perfil tributario; la clasificación final es de la DGII.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

from erpnext_rd.dgii_reportes.declaraciones import vencimiento
from erpnext_rd.nomina_rd import feriados

DOCTYPE = "Base Anticipo ISR"
DIA_VENCE_ANTICIPO = 15
MENSUAL = "Mensual"
TRES_CUOTAS = "Tres cuotas"
EXENTO = "Exento"
CUOTAS_PEQUENAS_POR_DEFECTO = "6:50, 9:30, 12:20"
LEY_30_26_DESDE = 2026
TASA_MINIMA_POR_DEFECTO = 1.5
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


def tasa_minima() -> float:
	return (
		flt(frappe.db.get_single_value("Configuracion DGII", "anticipo_tasa_minima"))
		or TASA_MINIMA_POR_DEFECTO
	)


def calcular(ingresos_brutos: float, impuesto_liquidado: float, minima: float) -> frappe._dict:
	"""Tasa efectiva (%), método y cuota mensual del anticipo."""
	ingresos, impuesto = flt(ingresos_brutos), flt(impuesto_liquidado)
	tasa = impuesto * 100 / ingresos if ingresos > 0 else 0.0
	if tasa > minima:
		return frappe._dict(
			tasa_efectiva=tasa,
			metodo=_("Doceava parte del impuesto liquidado"),
			cuota=flt(impuesto / 12, 2),
		)
	return frappe._dict(
		tasa_efectiva=tasa,
		metodo=_("{0}% de los ingresos brutos, en 12 cuotas").format(f"{minima:g}"),
		cuota=flt(ingresos * minima / 100 / 12, 2),
	)


def cuotas_pequenas() -> dict[int, float]:
	"""{mes del ejercicio: % del impuesto liquidado} de las pequeñas empresas (art. 314, párrafo II)."""
	texto = frappe.db.get_single_value("Configuracion DGII", "anticipo_cuotas_pequenas")
	return leer_cuotas(texto or CUOTAS_PEQUENAS_POR_DEFECTO)


def leer_cuotas(texto: str) -> dict[int, float]:
	"""«6:50, 9:30, 12:20» → {6: 50, 9: 30, 12: 20}. Meses de 1 a 12 y porcentajes que suman 100."""
	cuotas = {}
	try:
		for parte in (texto or "").split(","):
			mes, porcentaje = parte.split(":")
			cuotas[int(mes)] = float(porcentaje)
	except ValueError:
		frappe.throw(
			_("Cuotas de las pequeñas empresas no válidas: {0}. Ejemplo: 6:50, 9:30, 12:20").format(texto)
		)
	if not cuotas or any(m < 1 or m > 12 for m in cuotas) or flt(sum(cuotas.values()), 2) != 100:
		frappe.throw(
			_("Las cuotas de las pequeñas empresas deben ser meses de 1 a 12 y sumar 100%: {0}").format(texto)
		)
	return cuotas


def desde_ejercicio() -> int:
	return (
		cint(frappe.db.get_single_value("Configuracion DGII", "anticipo_ley_30_26_desde")) or LEY_30_26_DESDE
	)


def regimen_por_perfil(company: str, ejercicio: int) -> tuple[str, str | None]:
	"""Régimen que corresponde según el tamaño del perfil (Ley 30-26), con el motivo si es exento."""
	from erpnext_rd.rd_compliance import perfil

	p = perfil.perfil(company)
	# Las personas físicas ya pagaban en tres cuotas antes de la Ley 30-26
	if p.tipo_contribuyente == perfil.FISICA:
		return TRES_CUOTAS, None
	if cint(ejercicio) < desde_ejercicio():
		return MENSUAL, None
	if p.tamano == perfil.MICRO:
		return EXENTO, _("Microempresa (Código Tributario art. 314, párrafo III, según la Ley 30-26)")
	# Párrafo II: pequeñas empresas
	if p.tamano == perfil.PEQUENA:
		return TRES_CUOTAS, None
	return MENSUAL, None


def describir_cuotas(cuotas: dict[int, float]) -> str:
	return _("100% del impuesto liquidado en tres cuotas: {0}").format(
		", ".join(_("mes {0} del ejercicio {1}%").format(m, f"{p:g}") for m, p in sorted(cuotas.items()))
	)


def inicio_por_defecto(ejercicio: int) -> date:
	"""Cierre al 31 de diciembre: el IR-2 vence el 30 de abril y la base nueva rige desde mayo."""
	return date(cint(ejercicio) + 1, 5, 1)


def vence(anio: int, mes: int) -> date:
	return feriados.dia_habil(vencimiento(anio, mes, DIA_VENCE_ANTICIPO))


def base_vigente(company: str, fecha) -> frappe._dict | None:
	"""La base registrada más reciente que ya rige en `fecha` (un vencimiento)."""
	bases = frappe.get_all(
		DOCTYPE,
		filters={"company": company, "aplica_desde": ("<=", getdate(fecha))},
		fields=["name", "ejercicio", "regimen", "metodo", "cuota_mensual", "impuesto_liquidado"],
		order_by="aplica_desde desc, ejercicio desc",
		limit=1,
	)
	return bases[0] if bases else None


def anticipo(company: str, anio: int, mes: int) -> frappe._dict | None:
	"""Anticipo del período (año, mes): cuota, vencimiento y la base usada. None si no hay que pagar."""
	limite = vencimiento(anio, mes, DIA_VENCE_ANTICIPO)
	base = base_vigente(company, limite)
	if base and base.regimen == TRES_CUOTAS:
		return _cuota_pequena(company, anio, mes, base)
	if not base or base.regimen != MENSUAL or not flt(base.cuota_mensual):
		return None
	return frappe._dict(
		periodo=f"{MESES[cint(mes) - 1]} {anio}",
		vence=vence(anio, mes),
		cuota=flt(base.cuota_mensual),
		base=base.name,
		ejercicio=base.ejercicio,
		metodo=base.metodo,
	)


def _cuota_pequena(company: str, anio: int, mes: int, base) -> frappe._dict | None:
	"""Cuota de una pequeña empresa si (año, mes) es uno de sus meses del ejercicio."""
	from erpnext_rd.rd_compliance import perfil

	inicio, _fin = perfil.periodo_fiscal(company, date(anio, mes, 1))
	mes_del_ejercicio = (anio - inicio.year) * 12 + mes - inicio.month + 1
	porcentaje = cuotas_pequenas().get(mes_del_ejercicio)
	if not porcentaje or not flt(base.impuesto_liquidado):
		return None
	return frappe._dict(
		periodo=f"{MESES[cint(mes) - 1]} {anio}",
		vence=feriados.dia_habil(get_last_day(date(anio, mes, 1))),
		cuota=flt(flt(base.impuesto_liquidado) * porcentaje / 100, 2),
		base=base.name,
		ejercicio=base.ejercicio,
		metodo=_("Pequeña empresa: {0}% del impuesto liquidado (mes {1} del ejercicio)").format(
			f"{porcentaje:g}", mes_del_ejercicio
		),
	)


def reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "periodo", "label": _("Período"), "fieldtype": "Data", "width": 160},
		{"fieldname": "vence", "label": _("Vence"), "fieldtype": "Date", "width": 110},
		{"fieldname": "cuota", "label": _("Anticipo"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "base", "label": _("Base"), "fieldtype": "Link", "options": DOCTYPE, "width": 140},
		{"fieldname": "ejercicio", "label": _("Año declarado"), "fieldtype": "Int", "width": 120},
		{"fieldname": "metodo", "label": _("Cálculo"), "fieldtype": "Data", "width": 300},
	]
	if not (filters.company and filters.anio):
		return columnas, []

	anio = cint(filters.anio)
	filas = []
	for mes in range(1, 13):
		a = anticipo(filters.company, anio, mes)
		filas.append(
			a
			or {
				"periodo": f"{MESES[mes - 1]} {anio}",
				"vence": vence(anio, mes),
				"cuota": 0.0,
				"metodo": _("Sin anticipo: no hay base vigente o la empresa está exenta"),
			}
		)
	total = sum(flt(f["cuota"]) for f in filas)
	resumen = [
		{"label": _("Anticipos del año"), "value": total, "datatype": "Currency", "indicator": "Blue"},
	]
	hoy = getdate()
	proximo = next((f for f in filas if f["cuota"] and getdate(f["vence"]) >= hoy), None)
	if proximo:
		resumen.append(
			{
				"label": _("Próximo vencimiento"),
				"value": proximo["vence"],
				"datatype": "Date",
				"indicator": "Red",
			}
		)
	mensaje = _(
		"Anticipos del ISR por período, con la base del IR-2 registrada en «Base Anticipo ISR». El "
		"anticipo mensual vence el día 15 del mes siguiente; el de las pequeñas empresas (tres cuotas), el "
		"último día de su mes (o el siguiente día hábil). Los anticipos pagados son crédito en el IR-2 del "
		"año. Verifique los montos con su contador."
	)
	return columnas, filas, mensaje, None, resumen
