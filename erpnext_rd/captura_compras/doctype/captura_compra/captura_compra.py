# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from erpnext_rd.captura_compras import qr
from erpnext_rd.captura_compras.convertir import TIPOS_CAPTURA
from erpnext_rd.dgii_fiscal.identificacion import identificacion_valida
from erpnext_rd.ecf.emision import rnc_empresa

CERRADOS = ("Factura creada", "Duplicada", "Descartada")


class CapturaCompra(Document):
	def validate(self):
		if self.url_timbre and (self.is_new() or self.has_value_changed("url_timbre")):
			self.update(qr.leer_url(self.url_timbre))
		# El ITBIS escrito a mano en el escritorio (la DGII y el PDF ponen su propia fuente)
		if (
			not self.is_new()
			and self.has_value_changed("total_itbis")
			and not self.has_value_changed("fuente_montos")
		):
			self.fuente_montos = "Manual"
		self.encf = (self.encf or "").strip().upper() or None
		self.tipo_ecf = self.encf[:3] if self.encf else None
		self._validar_comprador()
		self._proveedor()
		self._duplicados()
		self._estado()

	def after_insert(self):
		if self.encf and self.codigo_seguridad:
			frappe.enqueue(
				"erpnext_rd.captura_compras.api.verificar_en_segundo_plano",
				queue="short",
				name=self.name,
				enqueue_after_commit=True,
			)

	def _validar_comprador(self):
		rnc = rnc_empresa(self.company)
		if self.rnc_comprador and self.rnc_comprador != rnc:
			frappe.throw(
				_("La factura es a nombre del RNC {0}, no de {1} ({2}): no sirve para el 606.").format(
					self.rnc_comprador, self.company, rnc
				),
				title=_("Factura de otra empresa"),
			)
		if self.rnc_emisor and not identificacion_valida(self.rnc_emisor):
			frappe.throw(_("El RNC del emisor {0} no es válido.").format(self.rnc_emisor))

	def _proveedor(self):
		if not self.rnc_emisor:
			return
		if not self.proveedor:
			self.proveedor = frappe.db.get_value("Supplier", {"tax_id": self.rnc_emisor}, "name")
		if not self.razon_social_emisor:
			self.razon_social_emisor = (
				frappe.db.get_value("Supplier", self.proveedor, "supplier_name")
				if self.proveedor
				else frappe.db.get_value("Contribuyente DGII", self.rnc_emisor, "razon_social")
			)

	def _duplicados(self):
		if not (self.encf and self.rnc_emisor):
			return
		filtros = {"company": self.company, "rnc_emisor": self.rnc_emisor, "encf": self.encf}
		otra = frappe.db.get_value(
			self.doctype, {**filtros, "estado": ("!=", "Descartada"), "name": ("!=", self.name or "")}
		)
		if otra:
			frappe.throw(_("Esta factura ya se capturó en {0}.").format(otra), title=_("Factura repetida"))
		if not self.ecf_recibido:
			self.ecf_recibido = frappe.db.get_value("ECF Recibido", {**filtros, "estado": "Recibido"})
		if not self.factura_compra and self.proveedor:
			self.factura_compra = frappe.db.get_value(
				"Purchase Invoice",
				{
					"company": self.company,
					"supplier": self.proveedor,
					"rd_ncf": self.encf,
					"docstatus": ("<", 2),
				},
			)
			if self.factura_compra:
				self.estado = "Duplicada"

	def _estado(self):
		if self.estado in CERRADOS:
			return
		avisos = []
		if not self.encf:
			avisos.append(_("Falta el e-NCF: escanee el QR o escríbalo."))
		elif self.tipo_ecf not in TIPOS_CAPTURA:
			avisos.append(_("Los e-CF {0} se registran a mano.").format(self.tipo_ecf))
		if self.estado_dgii in ("Rechazado", "No encontrado"):
			avisos.append(_("La DGII responde: {0}.").format(_(self.estado_dgii)))
		if self.fuente_montos and flt(self.total_itbis) > flt(self.monto_total):
			avisos.append(_("El ITBIS es mayor que el total."))
		if avisos:
			self.estado, self.avisos = "Requiere revisión", "\n".join(avisos)
		else:
			self.estado = "Lista" if self.fuente_montos else "Pendiente"
			if self.avisos and not self.ecf_recibido:
				self.avisos = None
