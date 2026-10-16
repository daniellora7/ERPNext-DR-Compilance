from frappe import _


def boot_session(bootinfo):
	traducir_dock(bootinfo)


def traducir_dock(bootinfo):
	"""Traduce los nombres del dock al idioma del usuario.

	El dock de Frappe v16 muestra el título guardado de cada entrada sin pasarlo por `__()`, así que
	"Accounts" o "Payroll" salen en inglés aunque exista la traducción. Se traducen aquí, en la sesión
	de cada usuario, sin escribir nada en la base. Al guardar "Organizar dock", Frappe reconoce el
	título traducido como heredado (`settle_reference`) y no lo guarda como propio.
	"""
	for filas in (bootinfo.get("dock") or {}).values():
		_traducir_titulos(filas)
	for app in bootinfo.get("app_data") or []:
		_traducir_titulos(app.get("dock"))


def _traducir_titulos(filas):
	for fila in filas or []:
		if isinstance(fila, dict) and fila.get("title"):
			fila["title"] = _(fila["title"])
