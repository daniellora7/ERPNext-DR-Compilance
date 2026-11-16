# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_reportes import ir1, ir2
from erpnext_rd.rd_compliance import perfil


class CuadreFiscalIR1(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("El cuadre del IR-1 solo aplica a empresas de República Dominicana"))
		if not perfil.declara_ir1(self.company):
			frappe.throw(
				_(
					"Según su perfil tributario, {0} no declara el IR-1 (solo las personas físicas con negocio "
					"del régimen ordinario)."
				).format(self.company)
			)
		duplicado = frappe.db.exists(
			ir1.DOCTYPE,
			{
				"company": self.company,
				"ejercicio": self.ejercicio,
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
		)
		if duplicado:
			frappe.throw(
				_("Ya existe el cuadre del IR-1 del año {0} para {1}: {2}").format(
					self.ejercicio, self.company, duplicado
				)
			)
		self.desde = date(cint(self.ejercicio), 1, 1)
		self.hasta = date(cint(self.ejercicio), 12, 31)
		if self.is_new() and not flt(self.ingresos):
			self.traer_datos()
		self.calcular()

	def traer_datos(self):
		"""Ingresos y beneficio antes del ISR (como el anexo B-1), gastos con NCF no válido y anticipos."""
		from erpnext_rd.dgii_reportes import estados_ir2

		self.desde = date(cint(self.ejercicio), 1, 1)
		self.hasta = date(cint(self.ejercicio), 12, 31)
		estados = estados_ir2.calcular(self.company, self.desde, self.hasta)
		self.ingresos = estados.totales_b1["4"]
		self.beneficio_contable = estados.totales_b1["14"]
		avisos = list(estados.avisos)
		gastos = ir2.gastos_con_ncf_invalido(self.company, self.desde, self.hasta)
		if gastos and not flt(self.gastos_no_admitidos):
			self.gastos_no_admitidos = gastos
			avisos.append(
				_("Compras con NCF no válido en la DGII propuestas como gastos no admitidos: {0}").format(
					frappe.format(gastos, "Currency")
				)
			)
		self.anticipos_pagados = ir2.anticipos_del_ejercicio(self.company, self.desde, self.hasta)
		self.avisos = "\n".join(avisos)

	def calcular(self):
		pedido = flt(self.gastos_educacion)
		self.update(ir1.liquidar(frappe._dict(self.as_dict()), cint(self.ejercicio)))
		if pedido > flt(self.gastos_educacion):
			frappe.msgprint(
				_(
					"Los gastos en educación se limitaron a {0} (10% de la renta y 25% de la exención)."
				).format(frappe.format(self.gastos_educacion, "Currency")),
				indicator="orange",
				alert=True,
			)
