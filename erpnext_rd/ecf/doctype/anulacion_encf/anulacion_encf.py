# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

"""Anulación de rangos de e-NCF no utilizados (ANECF).

Al validar: se firma la anulación, se envía a la DGII (si el emisor envía) y cada secuencia salta el
rango anulado para no volver a usar esos números. Un e-NCF ya usado (factura aprobada o e-CF aceptado,
en proceso o en contingencia) no se puede anular: se corrige con una nota de crédito."""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_fiscal.validaciones import formatear_ncf
from erpnext_rd.ecf import datos, esquemas, firma
from erpnext_rd.ecf.cliente import ClienteDGII, ErrorDGII
from erpnext_rd.ecf.emision import ENVIO, emisor_de, guardar_xml, leer_xml, mensajes, rnc_empresa

SECUENCIA = "Secuencia NCF"
# e-CF que ya cuentan para la DGII: no se anulan
USADOS = ("En proceso", "Contingencia", "Aceptado", "Aceptado condicional")
MAXIMO_RANGOS_POR_TIPO = 10000


class AnulacionENCF(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("La anulación de e-NCF es solo para empresas de República Dominicana."))
		vistos = defaultdict(list)
		for fila in self.rangos:
			self._validar_rango(fila, vistos[fila.secuencia])
			vistos[fila.secuencia].append((fila.desde, fila.hasta))
		self.cantidad = sum(cint(f.cantidad) for f in self.rangos)
		if self.docstatus == 0:
			self.estado = "Borrador"

	def _validar_rango(self, fila, anteriores):
		seq = frappe.db.get_value(
			SECUENCIA,
			fila.secuencia,
			["company", "tipo_comprobante", "serie", "desde", "hasta"],
			as_dict=True,
		)
		if seq.company != self.company:
			frappe.throw(_("Fila {0}: la secuencia {1} es de otra empresa.").format(fila.idx, fila.secuencia))
		if not (seq.tipo_comprobante or "").startswith("E"):
			frappe.throw(
				_("Fila {0}: solo se anulan rangos de e-NCF; los NCF en papel van en el 608.").format(
					fila.idx
				)
			)
		if not (seq.desde <= cint(fila.desde) <= cint(fila.hasta) <= seq.hasta):
			frappe.throw(
				_("Fila {0}: el rango debe estar dentro de la secuencia autorizada ({1} a {2}).").format(
					fila.idx, seq.desde, seq.hasta
				)
			)
		if any(cint(fila.desde) <= h and d <= cint(fila.hasta) for d, h in anteriores):
			frappe.throw(_("Fila {0}: el rango se cruza con otro de la misma secuencia.").format(fila.idx))

		fila.tipo_comprobante = seq.tipo_comprobante
		fila.encf_desde = formatear_ncf(seq.serie, seq.tipo_comprobante[1:], cint(fila.desde))
		fila.encf_hasta = formatear_ncf(seq.serie, seq.tipo_comprobante[1:], cint(fila.hasta))
		fila.cantidad = cint(fila.hasta) - cint(fila.desde) + 1

		entre = [["rd_ncf", ">=", fila.encf_desde], ["rd_ncf", "<=", fila.encf_hasta]]
		for doctype in ("Sales Invoice", "Purchase Invoice"):
			if usado := frappe.get_all(
				doctype,
				filters=[*entre, ["company", "=", self.company], ["docstatus", "=", 1]],
				pluck="rd_ncf",
				limit=1,
			):
				frappe.throw(
					_(
						"Fila {0}: el e-NCF {1} ya está en una factura aprobada; corríjalo con una nota de crédito."
					).format(fila.idx, usado[0])
				)
		if usado := frappe.get_all(
			ENVIO,
			filters=[
				["encf", ">=", fila.encf_desde],
				["encf", "<=", fila.encf_hasta],
				["company", "=", self.company],
				["estado", "in", USADOS],
			],
			pluck="encf",
			limit=1,
		):
			frappe.throw(_("Fila {0}: el e-CF {1} ya fue enviado a la DGII.").format(fila.idx, usado[0]))
		previa = frappe.get_all(
			"Anulacion ENCF Rango",
			filters={
				"parenttype": self.doctype,
				"docstatus": 1,
				"secuencia": fila.secuencia,
				"desde": ("<=", fila.hasta),
				"hasta": (">=", fila.desde),
			},
			pluck="parent",
			limit=1,
		)
		if previa:
			frappe.throw(_("Fila {0}: el rango ya se anuló en {1}.").format(fila.idx, previa[0]))

	def datos_anecf(self, fecha) -> dict:
		por_tipo = defaultdict(list)
		for fila in self.rangos:
			por_tipo[cint(fila.tipo_comprobante[1:])].append(fila)
		anulaciones = []
		for linea, (tipo, filas) in enumerate(sorted(por_tipo.items()), start=1):
			if len(filas) > MAXIMO_RANGOS_POR_TIPO:
				frappe.throw(_("Demasiados rangos del tipo E{0}.").format(tipo))
			anulaciones.append(
				{
					"NoLinea": linea,
					"TipoeCF": tipo,
					"TablaRangoSecuenciasAnuladaseNCF": {
						"Secuencias": [
							{"SecuenciaeNCFDesde": f.encf_desde, "SecuenciaeNCFHasta": f.encf_hasta}
							for f in filas
						]
					},
					"CantidadeNCFAnulados": sum(cint(f.cantidad) for f in filas),
				}
			)
		return {
			"Encabezado": {
				"Version": datos.VERSION,
				"RncEmisor": rnc_empresa(self.company),
				"CantidadeNCFAnulados": self.cantidad,
				"FechaHoraAnulacioneNCF": datos.fecha_hora(fecha),
			},
			"DetalleAnulacion": {"Anulacion": anulaciones},
		}

	def on_submit(self):
		emisor = emisor_de(self.company)
		llave, certificado = emisor.cargar()
		fecha = now_datetime()
		anecf = firma.firmar(esquemas.construir("ANECF", self.datos_anecf(fecha)), llave, certificado)
		esquemas.validar("ANECF", anecf)
		xml = guardar_xml(
			self.doctype, self.name, "xml", f"{rnc_empresa(self.company)}_ANECF_{self.name}.xml", anecf
		)
		self.db_set({"fecha_anulacion": fecha, "xml": xml, "estado": "Firmado"})
		self._saltar_rangos()
		if emisor.habilitado:
			self._enviar(emisor)

	def _saltar_rangos(self):
		"""La secuencia no vuelve a dar los números anulados."""
		for fila in self.rangos:
			seq = frappe.db.get_value(SECUENCIA, fila.secuencia, ["siguiente", "hasta"], as_dict=True)
			if cint(fila.desde) <= seq.siguiente <= cint(fila.hasta):
				siguiente = cint(fila.hasta) + 1
				disponibles = max(seq.hasta - siguiente + 1, 0)
				frappe.db.set_value(
					SECUENCIA,
					fila.secuencia,
					{
						"siguiente": siguiente,
						"disponibles": disponibles,
						"habilitada": 1 if disponibles else 0,
					},
					update_modified=False,
				)

	@frappe.whitelist(methods=["POST"])
	def enviar_dgii(self) -> str:
		"""Envía (o reenvía) la anulación firmada a la DGII."""
		self.check_permission("submit")
		return self._enviar(emisor_de(self.company))

	def _enviar(self, emisor: Document) -> str:
		if self.docstatus != 1 or self.estado in ("Aceptado", "Rechazado"):
			frappe.throw(_("Esta anulación no se puede enviar ({0}).").format(self.estado))
		llave, certificado = emisor.cargar()
		cliente = ClienteDGII(rnc_empresa(self.company), llave, certificado)
		try:
			respuesta = cliente.anular_rangos(leer_xml(self.xml), self.xml.rsplit("/", 1)[-1])
			cambios = {
				"estado": estado_anulacion(respuesta),
				"respuesta": json.dumps(respuesta, ensure_ascii=False, indent=1),
				"mensajes": mensajes(respuesta),
			}
		except (ErrorDGII, OSError) as error:
			cambios = {"estado": "Error", "mensajes": str(error)}
		self.db_set(cambios)
		return self.estado


def estado_anulacion(respuesta) -> str:
	"""Estado de la respuesta de la DGII: Aceptado, Rechazado o, si no lo dice, Enviado."""
	if not isinstance(respuesta, dict):
		return "Enviado"
	texto = " ".join(str(respuesta.get(c) or "") for c in ("estado", "nombre", "codigo")).lower()
	if "rechaz" in texto:
		return "Rechazado"
	if "acept" in texto or "anulad" in texto:
		return "Aceptado"
	return "Enviado"
