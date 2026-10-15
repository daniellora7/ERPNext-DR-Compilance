"""Feriados de República Dominicana en la *Holiday List* de ERPNext.

Los feriados salen de la librería `holidays` (la misma que usa el botón "Agregar feriados locales"
de la lista), que ya aplica los traslados de la Ley 139-97. Se mantiene una sola lista, "Feriados RD",
que se extiende hasta el 31 de diciembre del año siguiente; solo se agregan fechas de los años
nuevos, así lo que el usuario edite (p. ej. un decreto que mueva un feriado) se conserva.
"""

import frappe
from frappe.utils import add_days, getdate, today

from erpnext_rd.dgii_fiscal.ncf import PAIS

LISTA = "Feriados RD"
CODIGO_PAIS = "DO"
DIAS = {
	"Sunday": "Domingo",
	"Monday": "Lunes",
	"Tuesday": "Martes",
	"Wednesday": "Miércoles",
	"Thursday": "Jueves",
	"Friday": "Viernes",
	"Saturday": "Sábado",
}


def asegurar_lista_feriados():
	"""Crea o extiende la lista y la deja por defecto en las empresas RD sin lista. Idempotente."""
	conf = frappe.get_single("Configuracion Nomina RD")
	empresas = frappe.get_all("Company", filters={"country": PAIS}, fields=["name", "default_holiday_list"])
	if not (conf.actualizar_feriados and empresas):
		return

	hasta = getdate(f"{getdate(today()).year + 1}-12-31")
	if frappe.db.exists("Holiday List", LISTA):
		lista = frappe.get_doc("Holiday List", LISTA)
		anterior = getdate(lista.to_date)
		if anterior < hasta:
			lista.to_date = hasta
			agregar_feriados(lista, add_days(anterior, 1), hasta, conf.dia_descanso)
			lista.save(ignore_permissions=True)
	else:
		desde = getdate(f"{getdate(today()).year}-01-01")
		lista = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": LISTA,
				"from_date": desde,
				"to_date": hasta,
				"country": CODIGO_PAIS,
				"weekly_off": conf.dia_descanso or None,
			}
		)
		agregar_feriados(lista, desde, hasta, conf.dia_descanso)
		lista.insert(ignore_permissions=True)

	for empresa in empresas:
		if not empresa.default_holiday_list:
			frappe.db.set_value("Company", empresa.name, "default_holiday_list", LISTA)
	if conf.lista_feriados != LISTA:
		frappe.db.set_single_value("Configuracion Nomina RD", "lista_feriados", LISTA)


def agregar_feriados(lista, desde, hasta, descanso: str | None = None):
	"""Agrega a la lista los feriados RD y los días de descanso entre dos fechas, sin repetir fechas."""
	from holidays import country_holidays

	desde, hasta = getdate(desde), getdate(hasta)
	existentes = set(lista.get_holidays())
	anios = range(desde.year, hasta.year + 1)
	for fecha, nombre in sorted(country_holidays(CODIGO_PAIS, years=anios, language="es").items()):
		if desde <= fecha <= hasta and fecha not in existentes:
			lista.append("holidays", {"holiday_date": fecha, "description": nombre, "weekly_off": 0})
			existentes.add(fecha)

	if descanso:
		# ERPNext toma el día de la lista, no de un argumento
		lista.weekly_off = descanso
		for fecha in lista.get_weekly_off_date_list(desde, hasta):
			if fecha not in existentes:
				lista.append(
					"holidays",
					{"holiday_date": fecha, "description": DIAS.get(descanso, descanso), "weekly_off": 1},
				)
				existentes.add(fecha)
