"""Service worker de la pantalla para escanear facturas (/rd-compliance/escanear).

Un service worker solo controla las páginas bajo su propia ruta, y los archivos de /assets no
están bajo /rd-compliance/. Por eso se sirve desde /rd-compliance-sw.js (alcance máximo "/", la
página lo registra con alcance /rd-compliance/). No va bajo /rd-compliance/ porque esa ruta la toma
la regla de website_route_rules antes que los page_renderer."""

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

RUTA = "rd-compliance-sw.js"


class ServiceWorker(BaseRenderer):
	"""page_renderer de hooks.py."""

	def can_render(self):
		return self.path == RUTA

	def render(self):
		with open(frappe.get_app_path("erpnext_rd", "public", "pwa", "sw.js"), encoding="utf-8") as archivo:
			respuesta = Response(archivo.read(), mimetype="application/javascript")
		# El navegador revisa si cambió en cada visita
		respuesta.headers["Cache-Control"] = "no-cache"
		return respuesta
