"""Sidebars de la app y la entrada de Nómina RD en el dock de Frappe HR."""

import frappe

from erpnext_rd.nomina_rd import hrms_instalado

# Sidebar de la Nómina RD (nomina_rd/sidebar): vive en el dock de Frappe HR, no en RD Compliance
SIDEBAR_NOMINA = "Nomina RD"
FILA_DOCK_NOMINA = {"link_type": "Sidebar", "link_to": SIDEBAR_NOMINA}
# Ícono "soft" del dock (estilo de Frappe v16.52+); el de dos tonos queda para el encabezado del sidebar
ICONO_DOCK_NOMINA = "nomina-rd-soft"
ICONOS_DOCK_NOMINA_ANTERIORES = ("nomina-rd-duotone",)


def asegurar_navegacion():
	"""Importa los sidebars de la app (RD Compliance y Nómina RD) si faltan.

	Al agregar un módulo a un sitio existente, su sidebar se sincroniza antes de que exista el
	Module Def y queda fuera hasta el siguiente migrate. Esto lo deja listo en la misma pasada.
	"""
	from frappe.modules.import_file import import_file_by_path

	for modulo, nombre in (("rd_compliance", "RD Compliance"), ("nomina_rd", SIDEBAR_NOMINA)):
		if frappe.db.exists("Sidebar", nombre):
			continue
		carpeta = frappe.scrub(nombre)
		import_file_by_path(
			frappe.get_app_path("erpnext_rd", modulo, "sidebar", carpeta, f"{carpeta}.json"), force=True
		)


def dock_nomina():
	"""Pone "Nómina RD" en el dock de Frappe HR si está instalado; si no, lo quita.

	Una app solo monta su dock sobre una app (el nuestro va en ERPNext con RD Compliance), así que la
	nómina entra por la capa del sitio del dock de Frappe HR, la misma que guarda "Organizar dock".
	No se toca el archivo de HRMS. Si el sitio no tenía arreglo propio, se crea con el orden de HRMS
	y la nómina al final; si ya lo tenía, solo se agrega la fila (y un usuario la puede ocultar).
	"""
	if not frappe.db.exists("DocType", "Dock"):
		return
	if not hrms_instalado():
		quitar_dock_nomina()
		return
	from frappe.desk.doctype.dock.dock import SITE_LAYER, get_app_base

	capas = _capas_dock_hrms()
	sitio = next((capa for capa in capas if not capa.user), None)
	if not sitio:
		sitio = frappe.new_doc("Dock")
		sitio.app, sitio.user = "hrms", SITE_LAYER
		for fila in get_app_base("hrms"):
			sitio.append("items", {**_destino(fila), "hidden": fila.get("hidden") or 0, "added": 0})
		capas.append(sitio)

	for capa in capas:
		existente = next((fila for fila in capa.items if _es_fila_nomina(fila)), None)
		if existente:
			# Sitios que ya tenían la entrada con el ícono anterior; uno elegido por el usuario se respeta
			if existente.icon in ICONOS_DOCK_NOMINA_ANTERIORES:
				existente.icon = ICONO_DOCK_NOMINA
				capa.save(ignore_permissions=True)
			continue
		# La capa del sitio trae la entrada (con ícono y título); la de un usuario solo la nombra,
		# porque una capa guardada es el dock completo y lo que no nombra no aparece.
		if capa is sitio:
			capa.append(
				"items", {**FILA_DOCK_NOMINA, "icon": ICONO_DOCK_NOMINA, "title": "Nómina RD", "added": 1}
			)
		else:
			capa.append("items", {**FILA_DOCK_NOMINA, "added": 0})
		capa.save(ignore_permissions=True)


def quitar_dock_nomina():
	"""Quita "Nómina RD" del dock de Frappe HR. Si la capa del sitio queda igual al dock de HRMS
	(la creó esta app y nadie la cambió), se borra para que el sitio vuelva al de HRMS."""
	if not frappe.db.exists("DocType", "Dock"):
		return
	from frappe.desk.doctype.dock.dock import get_app_dock

	base = (
		[(_destino(fila), fila.get("hidden") or 0) for fila in get_app_dock("hrms")]
		if hrms_instalado()
		else None
	)
	for capa in _capas_dock_hrms():
		filas = [fila for fila in capa.items if not _es_fila_nomina(fila)]
		if len(filas) == len(capa.items):
			continue
		sin_cambios = [
			(_destino(fila), fila.hidden or 0)
			for fila in filas
			if not (fila.added or fila.icon or fila.title)
		]
		if not capa.user and base is not None and len(sin_cambios) == len(filas) and sin_cambios == base:
			frappe.delete_doc("Dock", capa.name, force=True, ignore_permissions=True)
			continue
		capa.set("items", filas)
		capa.save(ignore_permissions=True)


def _capas_dock_hrms() -> list:
	"""Capas del dock de Frappe HR que no son el archivo de la app: la del sitio y las de usuarios."""
	return [
		frappe.get_doc("Dock", nombre)
		for nombre in frappe.get_all("Dock", filters={"app": "hrms", "standard": 0}, pluck="name")
	]


def _destino(fila) -> dict:
	return {campo: fila.get(campo) or None for campo in ("link_type", "link_to", "url")}


def _es_fila_nomina(fila) -> bool:
	return fila.get("link_type") == "Sidebar" and fila.get("link_to") == SIDEBAR_NOMINA
