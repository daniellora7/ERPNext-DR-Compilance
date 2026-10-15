"""Cálculos de nómina de República Dominicana: aportes a la TSS (Ley 87-01) e ISR de asalariados.

Las tasas, topes y la escala del ISR salen de *Configuracion Nomina RD* (editables, cambian por
ley o resolución). Todos los montos son mensuales salvo que se diga lo contrario.
"""

import frappe
from frappe.utils import cint, flt, getdate, today

# Escalas anuales del ISR (art. 296 del Código Tributario) usadas para inicializar la configuración.
# desde, hasta, tasa %, cuota fija.
ESCALA_ISR_2026 = [
	(0, 416_220.00, 0, 0),
	(416_220.01, 624_329.00, 15, 0),
	(624_329.01, 867_123.00, 20, 31_216.00),
	(867_123.01, None, 25, 79_776.00),
]
# Ley 30-26 (art. 10, nuevo art. 296): exento hasta RD$480,000 y tramo de 27% desde RD$4.8 millones.
# Desde 2028 se ajusta cada año por la inflación del año anterior (la publica la DGII).
ESCALA_ISR_2027 = [
	(0, 480_000.00, 0, 0),
	(480_000.01, 685_000.00, 15, 0),
	(685_000.01, 910_000.00, 20, 30_750.00),
	(910_000.01, 4_800_000.00, 25, 75_750.00),
	(4_800_000.01, None, 27, 1_048_250.00),
]
ESCALAS_ISR = {2026: ESCALA_ISR_2026, 2027: ESCALA_ISR_2027}


def configuracion():
	return frappe.get_cached_doc("Configuracion Nomina RD")


def _tope(conf, salarios: float) -> float:
	return flt(conf.salario_minimo_cotizable) * flt(salarios)


def aportes_tss(salario_cotizable: float, conf=None) -> frappe._dict:
	"""Aportes mensuales a la TSS de un salario cotizable, con los topes de cada rama.

	Devuelve los descuentos del empleado (afp, sfs) y los aportes del empleador
	(afp_empleador, sfs_empleador, srl, infotep).
	"""
	conf = conf or configuracion()
	salario = max(flt(salario_cotizable), 0.0)
	base_afp = min(salario, _tope(conf, conf.tope_afp_salarios))
	base_sfs = min(salario, _tope(conf, conf.tope_sfs_salarios))
	base_srl = min(salario, _tope(conf, conf.tope_srl_salarios))

	r = frappe._dict(
		afp=flt(base_afp * flt(conf.afp_empleado) / 100, 2),
		sfs=flt(base_sfs * flt(conf.sfs_empleado) / 100, 2),
		afp_empleador=flt(base_afp * flt(conf.afp_empleador) / 100, 2),
		sfs_empleador=flt(base_sfs * flt(conf.sfs_empleador) / 100, 2),
		srl=flt(base_srl * flt(conf.srl_empleador) / 100, 2),
		infotep=flt(salario * flt(conf.infotep_empleador) / 100, 2),
	)
	r.total_empleado = r.afp + r.sfs
	r.total_empleador = r.afp_empleador + r.sfs_empleador + r.srl + r.infotep
	return r


def escala_isr(conf, anio=None) -> list:
	"""Tramos de la escala del año: la del año más reciente que no pase de `anio` (por defecto el
	actual). Si `anio` es anterior a todas, la más antigua. Filas sin año = una sola escala."""
	anio = cint(anio) or getdate(today()).year
	anios = sorted({cint(t.get("anio")) for t in conf.escala_isr})
	if not anios:
		return []
	vigente = max((a for a in anios if a <= anio), default=anios[0])
	return sorted((t for t in conf.escala_isr if cint(t.get("anio")) == vigente), key=lambda t: flt(t.desde))


def isr_anual(renta_anual: float, conf=None, anio=None) -> float:
	"""ISR anual según la escala progresiva del año: cuota fija del tramo + tasa sobre el excedente."""
	conf = conf or configuracion()
	renta = flt(renta_anual)
	impuesto = 0.0
	for tramo in escala_isr(conf, anio):
		if renta < flt(tramo.desde):
			break
		# El excedente se mide desde el límite superior del tramo anterior (desde - 0.01)
		inicio = max(flt(tramo.desde) - 0.01, 0.0) if flt(tramo.desde) else 0.0
		impuesto = flt(tramo.cuota_fija) + (renta - inicio) * flt(tramo.tasa) / 100
	return flt(max(impuesto, 0.0), 2)


def isr_mensual(salario_gravable_mensual: float, conf=None, anio=None) -> float:
	"""Retención mensual de ISR: se anualiza la renta gravable del mes y se divide entre 12.

	`salario_gravable_mensual` = salario + otros ingresos gravados - aportes del empleado a la TSS.
	"""
	return flt(isr_anual(flt(salario_gravable_mensual) * 12, conf, anio) / 12, 2)


def regalia_pascual(salarios_ordinarios_del_anio: float) -> float:
	"""Salario de Navidad (art. 219 del Código de Trabajo): la duodécima parte de los salarios
	ordinarios devengados en el año. Está exento de ISR y de aportes a la TSS."""
	return flt(flt(salarios_ordinarios_del_anio) / 12, 2)
