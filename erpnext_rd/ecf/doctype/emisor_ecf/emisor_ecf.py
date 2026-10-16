# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.ecf import firma


class EmisorECF(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("El emisor electrónico es solo para empresas de República Dominicana."))
		if not self.certificado:
			self.titular = self.vigente_desde = self.vigente_hasta = None
			return
		self._archivo_privado()
		try:
			_llave, certificado = self.cargar()
		except ValueError:
			frappe.throw(_("No se pudo abrir el certificado: revise el archivo .p12 y su contraseña."))
		datos = firma.datos_certificado(certificado)
		self.titular, self.vigente_desde, self.vigente_hasta = (
			datos["titular"],
			datos["desde"],
			datos["hasta"],
		)
		if getdate(self.vigente_hasta) < getdate(today()):
			frappe.msgprint(
				_("El certificado venció el {0}.").format(self.vigente_hasta), indicator="red", alert=True
			)

	def _archivo_privado(self):
		archivo = frappe.db.get_value(
			"File", {"file_url": self.certificado}, ["name", "is_private"], as_dict=True
		)
		if archivo and not archivo.is_private:
			doc = frappe.get_doc("File", archivo.name)
			doc.is_private = 1
			doc.save(ignore_permissions=True)
			self.certificado = doc.file_url

	def cargar(self):
		"""(llave privada, certificado) del .p12 del emisor."""
		if not self.certificado:
			frappe.throw(_("El emisor de {0} no tiene certificado digital.").format(self.company))
		archivo = frappe.get_doc("File", {"file_url": self.certificado})
		clave = (
			self.get_password("clave_certificado", raise_exception=False) if self.clave_certificado else None
		)
		return firma.cargar_certificado(archivo.get_content(), clave)
