"""Página del Panel RD Compliance (/rd-compliance). El HTML lo genera el build del frontend
(`frontend/`, frappe-ui) en www/rd-compliance.html."""

import frappe
from frappe import _
from frappe.translate import get_translations_from_apps

from erpnext_rd.dgii_reportes.formatos import ROLES

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/rd-compliance"
		raise frappe.Redirect

	if not set(ROLES) & set(frappe.get_roles()):
		frappe.throw(_("No tiene permiso para ver el Panel RD Compliance"), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	# Una petición GET no guarda la sesión: el token CSRF nuevo tiene que quedar guardado
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
		"user": frappe.session.user,
		"desk_theme": frappe.db.get_value("User", frappe.session.user, "desk_theme") or "Light",
		# Solo las de la app: todas las del sitio pesarían varios MB en cada carga
		"__messages": get_translations_from_apps(frappe.local.lang, ["erpnext_rd"]),
	}
	return context
