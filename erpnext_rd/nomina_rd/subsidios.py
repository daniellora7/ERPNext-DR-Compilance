"""Subsidios de la SISALRIL: enfermedad común, maternidad y lactancia (Ley 87-01, arts. 131 y 132).

El empleador registra la licencia en la plataforma de la SISALRIL. En enfermedad común y maternidad
la SISALRIL paga al empleador, que adelanta el subsidio al trabajador; la lactancia se paga directo a
la trabajadora. Aquí se lleva el registro de cada subsidio, su monto estimado y el reembolso:

- Enfermedad común (Res. CNSS 560-04): desde el 4.º día de incapacidad y hasta 26 semanas (182 días),
  60% del salario cotizable promedio de los últimos seis meses si la atención es ambulatoria, 40% si
  es hospitalaria. Requiere doce meses de cotización sin interrupción.
- Maternidad: la base reguladora (salario cotizable del mes anterior a la licencia) por tres, en tres
  pagos mensuales.
- Lactancia: doce meses, para salarios cotizables de hasta tres salarios mínimos: 33%, 12% o 6% del
  salario cotizable según el tramo (Res. CNSS 378-03).

Las tasas y plazos están en *Configuracion Nomina RD*. El monto es una estimación: el definitivo lo
calcula la SISALRIL con las cotizaciones del SUIR. El salario sale de los recibos de nómina aprobados
(Frappe HR); sin ellos se escribe a mano.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, flt, getdate

from erpnext_rd.nomina_rd import calculos, hrms_instalado

DOCTYPE = "Subsidio SISALRIL"
ENFERMEDAD = "Enfermedad común"
MATERNIDAD = "Maternidad"
LACTANCIA = "Lactancia"
AMBULATORIA = "Ambulatoria"
HOSPITALARIA = "Hospitalaria"
DIAS_MES = 30
MESES_LACTANCIA = 12


def _inicio_mes(fecha) -> date:
	fecha = getdate(fecha)
	return date(fecha.year, fecha.month, 1)


def salarios_cotizables(employee: str, company: str, fecha, meses: int) -> list[float]:
	"""Salario cotizable de cada uno de los `meses` meses anteriores al de `fecha` con recibos aprobados."""
	if not hrms_instalado():
		return []
	from erpnext_rd.nomina_rd import tss

	montos = []
	inicio = _inicio_mes(fecha)
	for atras in range(1, cint(meses) + 1):
		mes = add_months(inicio, -atras)
		desde, hasta = tss.periodo(mes.year, mes.month)
		recibo = tss._recibos(company, desde, hasta).get(employee)
		if recibo and flt(recibo.salario_ss):
			montos.append(flt(recibo.salario_ss))
	return montos


def porcentaje_lactancia(salario: float, conf) -> float:
	"""Tramo por salarios mínimos (el de la TSS): 0 si pasa de tres."""
	minimo = flt(conf.salario_minimo_cotizable)
	if not minimo or flt(salario) <= 0:
		return 0.0
	for salarios, campo in (
		(1, "lactancia_un_salario"),
		(2, "lactancia_dos_salarios"),
		(3, "lactancia_tres_salarios"),
	):
		if flt(salario) <= minimo * salarios:
			return flt(conf.get(campo))
	return 0.0


def calcular(
	tipo: str, desde, hasta, salario_base: float, atencion: str | None = None, conf=None
) -> frappe._dict:
	"""Días, porcentaje, monto mensual (lactancia) y monto total estimado del subsidio."""
	conf = conf or calculos.configuracion()
	salario = flt(salario_base)
	r = frappe._dict(
		dias=0, porcentaje=0.0, monto_mensual=0.0, monto=0.0, hasta=getdate(hasta) if hasta else None
	)

	if tipo == ENFERMEDAD:
		dias_licencia = date_diff(hasta, desde) + 1 if hasta else 0
		dias = min(dias_licencia, cint(conf.subsidio_dias_maximo)) - cint(conf.subsidio_dias_espera)
		r.dias = max(dias, 0)
		campo = (
			"subsidio_enfermedad_hospitalario"
			if atencion == HOSPITALARIA
			else "subsidio_enfermedad_ambulatorio"
		)
		r.porcentaje = flt(conf.get(campo))
		r.monto = flt(salario / DIAS_MES * r.dias * r.porcentaje / 100, 2)
	elif tipo == MATERNIDAD:
		meses = flt(conf.subsidio_maternidad_meses)
		r.porcentaje = 100.0
		r.monto_mensual = flt(salario, 2)
		r.monto = flt(salario * meses, 2)
	elif tipo == LACTANCIA:
		r.porcentaje = porcentaje_lactancia(salario, conf)
		r.monto_mensual = flt(salario * r.porcentaje / 100, 2)
		r.monto = flt(r.monto_mensual * MESES_LACTANCIA, 2)
		r.hasta = add_days(add_months(getdate(desde), MESES_LACTANCIA), -1)
	return r


def salario_base(tipo: str, employee: str, company: str, desde, conf=None) -> frappe._dict:
	"""Enfermedad: promedio de los meses configurados. Maternidad y lactancia: el mes anterior."""
	conf = conf or calculos.configuracion()
	meses = cint(conf.subsidio_meses_promedio) if tipo == ENFERMEDAD else 1
	montos = salarios_cotizables(employee, company, desde, meses)
	return frappe._dict(
		salario=flt(sum(montos) / len(montos), 2) if montos else 0.0, meses=len(montos), requeridos=meses
	)


@frappe.whitelist(methods=["POST"])
def salario_desde_nomina(name: str) -> dict:
	"""Botón del formulario: vuelve a tomar el salario de los recibos de nómina y recalcula."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	base = salario_base(doc.tipo, doc.employee, doc.company, doc.desde)
	if not base.meses:
		frappe.throw(
			_("No hay recibos de nómina aprobados antes de {0}.").format(frappe.format(doc.desde, "Date"))
		)
	doc.salario_base = base.salario
	doc.meses_cotizados = base.meses
	doc.save()
	return {"salario": base.salario, "meses": base.meses}
