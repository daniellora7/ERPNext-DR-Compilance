"""Página del Panel RD Compliance (/rd-compliance) y de la pantalla para escanear facturas
(/rd-compliance/escanear). El HTML lo genera el build del frontend (`frontend/`, frappe-ui) en
www/rd-compliance.html. Quien solo tiene el rol de captura ve únicamente la pantalla de escanear."""

import frappe
from frappe import _
from frappe.translate import get_translations_from_apps

from erpnext_rd.captura_compras.api import ROL as ROL_CAPTURA
from erpnext_rd.dgii_reportes.formatos import ROLES

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + (
			frappe.request.path or "/rd-compliance"
		)
		raise frappe.Redirect

	roles = set(frappe.get_roles())
	if not (set(ROLES) | {ROL_CAPTURA}) & roles:
		frappe.throw(_("No tiene permiso para ver el Panel RD Compliance"), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	# Una petición GET no guarda la sesión: el token CSRF nuevo tiene que quedar guardado
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
		"user": frappe.session.user,
		"solo_escanear": not set(ROLES) & roles,
		"desk_theme": frappe.db.get_value("User", frappe.session.user, "desk_theme") or "Light",
		# Solo las de la app: todas las del sitio pesarían varios MB en cada carga
		"__messages": get_translations_from_apps(frappe.local.lang, ["erpnext_rd"]),
	}
	return context
