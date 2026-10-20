"""Anticipos del ISR de las personas jurídicas (art. 314 del Código Tributario).

Cada año, con los datos de la declaración jurada (IR-2), se registra una *Base Anticipo ISR*:
- Tasa efectiva de tributación (TET) = impuesto liquidado / ingresos brutos.
- TET mayor que la tasa mínima (1.5%, editable en *Configuracion DGII*): el anticipo mensual es la
  doceava parte del impuesto liquidado.
- TET igual o menor: el anticipo es la tasa mínima sobre los ingresos brutos, en doce cuotas.

El anticipo de cada mes vence el día 15 del mes siguiente (o el siguiente día hábil). La base nueva
rige desde el mes siguiente a la fecha límite del IR-2: con cierre al 31 de diciembre, el primer
pago con la base nueva es el del 15 de mayo.

Desde 2027 la Ley 30-26 exime a las microempresas y pasa a las pequeñas a tres cuotas al año; la
DGII aún no publica los criterios de clasificación. Mientras tanto, una empresa exenta se registra
con régimen *Exento*.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext_rd.dgii_reportes.declaraciones import vencimiento
from erpnext_rd.nomina_rd import feriados

DOCTYPE = "Base Anticipo ISR"
DIA_VENCE_ANTICIPO = 15
MENSUAL = "Mensual"
EXENTO = "Exento"
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
		fields=["name", "ejercicio", "regimen", "metodo", "cuota_mensual"],
		order_by="aplica_desde desc, ejercicio desc",
		limit=1,
	)
	return bases[0] if bases else None


def anticipo(company: str, anio: int, mes: int) -> frappe._dict | None:
	"""Anticipo del período (año, mes): cuota, vencimiento y la base usada. None si no hay que pagar."""
	limite = vencimiento(anio, mes, DIA_VENCE_ANTICIPO)
	base = base_vigente(company, limite)
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
		"Anticipos del ISR por período, con la base del IR-2 registrada en «Base Anticipo ISR». Cada "
		"anticipo vence el día 15 del mes siguiente (o el siguiente día hábil). Los anticipos pagados son "
		"crédito en el IR-2 del año. Verifique los montos con su contador."
	)
	return columnas, filas, mensaje, None, resumen
