# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_reportes import ir2


def _concepto_cuenta(categoria: str, uso: str) -> str:
	return f"{categoria} - {uso.lower()}"


class CuadreFiscalIR2(Document):
	def validate(self):
		if not es_empresa_rd(self.company):
			frappe.throw(_("El cuadre del IR-2 solo aplica a empresas de República Dominicana"))
		duplicado = frappe.db.exists(
			ir2.DOCTYPE,
			{
				"company": self.company,
				"ejercicio": self.ejercicio,
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
		)
		if duplicado:
			frappe.throw(
				_("Ya existe el cuadre del ejercicio {0} para {1}: {2}").format(
					self.ejercicio, self.company, duplicado
				)
			)
		self.desde = self.desde or date(cint(self.ejercicio), 1, 1)
		self.hasta = self.hasta or date(cint(self.ejercicio), 12, 31)
		if getdate(self.hasta) <= getdate(self.desde):
			frappe.throw(_("El cierre del ejercicio debe ser posterior a su inicio"))
		if self.is_new() and not (self.cuentas or self.edificaciones or self.ajustes):
			self.traer_datos()
		self.calcular()

	# ------------------------------------------------------------------ datos de ERPNext

	def traer_datos(self):
		"""Toma de la contabilidad y de los activos lo que se puede calcular. Los balances iniciales
		vienen del cuadre del año anterior; sin él, se conservan los escritos a mano o se propone el
		valor en libros."""
		anterior = ir2.cuadre_anterior(self.company, self.ejercicio, None if self.is_new() else self.name)
		self.cuadre_anterior = anterior.name if anterior else None
		inicio = add_days(self.desde, -1)
		avisos = []

		self.multiplicador = ir2.multiplicador(self.hasta) or flt(self.multiplicador)
		if not self.multiplicador:
			avisos.append(
				_(
					"No hay multiplicador de inflación para el cierre {0}: agréguelo en Configuración DGII."
				).format(frappe.format(self.hasta, "Date"))
			)
		self.patrimonio_fiscal = ir2.patrimonio_contable(self.company, inicio)
		self.tasa_isr = ir2.tasa("tasa_isr_juridicas")
		resultado = ir2.resultado_contable(self.company, self.desde, self.hasta)
		self.beneficio_contable = resultado.beneficio
		self.ingresos_brutos = resultado.ingresos
		self.anticipos_pagados = ir2.anticipos_del_ejercicio(self.company, self.desde, self.hasta)

		activos = ir2.activos(self.company, self.desde, self.hasta)
		contable = ir2.depreciacion_contable(self.company, self.desde, self.hasta)
		previa = ir2.depreciacion_contable(self.company, None, inicio)

		def en_libros(a):
			return flt(a.total_asset_cost) - flt(a.opening_accumulated_depreciation) - previa.get(a.name, 0)

		sin_costo_fiscal = []
		self._traer_edificaciones(anterior, activos, contable, en_libros, sin_costo_fiscal)
		self._traer_cuentas(anterior, activos, contable, en_libros)
		self._traer_terrenos(anterior, activos, en_libros)

		otros = {d.concepto: d.valor_fiscal for d in self.distribucion}
		self.distribucion = []
		self.append(
			"distribucion",
			{"concepto": ir2.INVENTARIO, "valor_fiscal": ir2.inventario_contable(self.company, inicio)},
		)
		self.append(
			"distribucion", {"concepto": ir2.OTROS_ACTIVOS, "valor_fiscal": otros.get(ir2.OTROS_ACTIVOS)}
		)

		self.ajustes = [
			a
			for a in self.ajustes
			if not (a.origen == ir2.AUTOMATICO and a.concepto == ir2.GASTOS_SIN_COMPROBANTE)
		]
		gastos = ir2.gastos_con_ncf_invalido(self.company, self.desde, self.hasta)
		if gastos:
			self._ajuste_automatico(
				ir2.GASTOS_SIN_COMPROBANTE, gastos, _("Compras con NCF no válido en la DGII")
			)

		if not anterior:
			avisos.append(
				_(
					"Sin cuadre del año anterior: los balances iniciales se proponen con el valor en libros. "
					"Reemplácelos por el costo fiscal del IR-2 anterior (anexos D, D-1 y D-2)."
				)
			)
		elif sin_costo_fiscal:
			avisos.append(
				_(
					"Edificaciones sin costo fiscal en el cuadre anterior (se usó el valor en libros): {0}"
				).format(", ".join(sin_costo_fiscal))
			)
		sin_categoria = sorted(
			{
				a.asset_category
				for a in activos
				if not frappe.get_cached_value("Asset Category", a.asset_category, "rd_categoria_fiscal")
			}
		)
		if sin_categoria:
			avisos.append(
				_(
					"Categorías de activo sin categoría fiscal (se tomaron como categoría 3 o terreno): {0}"
				).format(", ".join(sin_categoria))
			)
		self.avisos = "\n".join(avisos)

	def _traer_edificaciones(self, anterior, activos, contable, en_libros, sin_costo_fiscal):
		previas = {e.asset: e for e in anterior.edificaciones if not e.fecha_retiro} if anterior else {}
		actuales = {e.asset: e for e in self.edificaciones}
		self.edificaciones = []
		for a in activos:
			if a.categoria != ir2.CATEGORIA_1:
				continue
			fila = {
				"asset": a.name,
				"asset_name": a.asset_name,
				"depreciacion_contable": contable.get(a.name, 0),
			}
			actual = actuales.get(a.name)
			if a.adicion:
				fila.update(costo_fiscal_inicial=0, adicion=a.total_asset_cost, fecha_adicion=a.ingreso)
			else:
				if a.name in previas:
					costo = previas[a.name].costo_fiscal_final
				elif not anterior and actual:
					costo = actual.costo_fiscal_inicial
				else:
					costo = en_libros(a)
					if anterior:
						sin_costo_fiscal.append(a.name)
				fila["costo_fiscal_inicial"] = costo
				# Mejoras escritas a mano en el formulario
				if actual and actual.adicion:
					fila.update(adicion=actual.adicion, fecha_adicion=actual.fecha_adicion)
			if a.retirado:
				fila.update(fecha_retiro=a.retiro, valor_retiro=ir2.valor_retiro(a.name))
			self.append("edificaciones", fila)

	def _traer_cuentas(self, anterior, activos, contable, en_libros):
		previas = {(c.categoria, c.uso): c.costo_fiscal_final for c in anterior.cuentas} if anterior else {}
		actuales = {(c.categoria, c.uso): c for c in self.cuentas}
		totales = {
			cuenta: frappe._dict(libros=0, adiciones=0, retiros=0, contable=0) for cuenta in ir2.CUENTAS
		}
		for a in activos:
			if a.categoria not in (ir2.CATEGORIA_2, ir2.CATEGORIA_3):
				continue
			t = totales[(a.categoria, a.uso)]
			if a.adicion:
				t.adiciones += flt(a.total_asset_cost)
			else:
				t.libros += en_libros(a)
			if a.retirado:
				t.retiros += ir2.valor_retiro(a.name)
			t.contable += contable.get(a.name, 0)

		self.cuentas = []
		for categoria, uso in ir2.CUENTAS:
			t = totales[(categoria, uso)]
			if anterior:
				balance = previas.get((categoria, uso), 0)
			elif (categoria, uso) in actuales:
				balance = actuales[(categoria, uso)].balance_inicial
			else:
				balance = t.libros
			if uso == ir2.ARRENDAMIENTO and not any((balance, t.adiciones, t.retiros, t.contable)):
				continue
			self.append(
				"cuentas",
				{
					"categoria": categoria,
					"uso": uso,
					"balance_inicial": balance,
					"adiciones": t.adiciones,
					"retiros": t.retiros,
					"depreciacion_contable": t.contable,
				},
			)

	def _traer_terrenos(self, anterior, activos, en_libros):
		terrenos = [a for a in activos if a.categoria == ir2.TERRENO]
		if anterior:
			self.terrenos_costo_inicial = anterior.terrenos_costo_final
		elif not self.terrenos_costo_inicial:
			self.terrenos_costo_inicial = sum(en_libros(a) for a in terrenos if not a.adicion)
		self.terrenos_adiciones = sum(flt(a.total_asset_cost) for a in terrenos if a.adicion)
		self.terrenos_retiros = sum(en_libros(a) for a in terrenos if a.retirado and not a.adicion)

	def _ajuste_automatico(self, concepto: str, monto: float, detalle: str):
		self.append(
			"ajustes",
			{"concepto": concepto, "monto": flt(monto, 2), "detalle": detalle, "origen": ir2.AUTOMATICO},
		)

	# ------------------------------------------------------------------ cálculo

	def calcular(self):
		valores_manuales = {d.concepto: flt(d.valor_fiscal) for d in self.distribucion}
		valores = [
			(ir2.INVENTARIO, valores_manuales.get(ir2.INVENTARIO, 0)),
			(ir2.CATEGORIA_1, sum(flt(e.costo_fiscal_inicial) for e in self.edificaciones)),
			*[(_concepto_cuenta(c.categoria, c.uso), flt(c.balance_inicial)) for c in self.cuentas],
			(ir2.TERRENO, flt(self.terrenos_costo_inicial)),
			(ir2.OTROS_ACTIVOS, valores_manuales.get(ir2.OTROS_ACTIVOS, 0)),
		]
		reparto = ir2.distribuir_ajuste(self.patrimonio_fiscal, valores, self.multiplicador)
		self.activos_no_monetarios = reparto.activos_no_monetarios
		self.base_ajuste = reparto.base
		self.ajuste_fiscal = reparto.ajuste
		ajustes = {f.concepto: f for f in reparto.filas}
		self.distribucion = []
		for concepto, valor in valores:
			if not valor and concepto not in (ir2.INVENTARIO, ir2.OTROS_ACTIVOS):
				continue
			fila = ajustes.get(concepto) or frappe._dict(porcentaje=0, ajuste=0)
			self.append(
				"distribucion",
				{
					"concepto": concepto,
					"valor_fiscal": valor,
					"porcentaje": fila.porcentaje,
					"ajuste": fila.ajuste,
				},
			)

		def ajuste_de(concepto):
			return flt(ajustes[concepto].ajuste) if concepto in ajustes else 0.0

		self._calcular_edificaciones(ajuste_de(ir2.CATEGORIA_1))
		for c in self.cuentas:
			r = ir2.depreciar_cuenta(
				c.balance_inicial,
				ajuste_de(_concepto_cuenta(c.categoria, c.uso)),
				c.adiciones,
				c.retiros,
				ir2.tasa_depreciacion(c.categoria, c.uso),
			)
			c.ajuste_fiscal = ajuste_de(_concepto_cuenta(c.categoria, c.uso))
			c.tasa = ir2.tasa_depreciacion(c.categoria, c.uso)
			c.adiciones_imponibles = r.adiciones_imponibles
			c.adicion_no_depreciada = r.adicion_no_depreciada
			c.base_depreciable = r.base
			c.depreciacion_fiscal = r.depreciacion
			c.costo_fiscal_final = r.costo_final
			if r.base < 0:
				frappe.msgprint(
					_(
						"Los retiros de la {0} ({1}) superan su balance: la diferencia es renta gravable "
						"(art. 287, literal e, VIII)."
					).format(c.categoria, c.uso.lower()),
					indicator="orange",
					alert=True,
				)

		self.terrenos_ajuste = ajuste_de(ir2.TERRENO)
		self.terrenos_costo_final = flt(
			flt(self.terrenos_costo_inicial)
			+ self.terrenos_ajuste
			+ flt(self.terrenos_adiciones)
			- flt(self.terrenos_retiros),
			2,
		)

		filas = [*self.edificaciones, *self.cuentas]
		self.depreciacion_fiscal = flt(sum(flt(f.depreciacion_fiscal) for f in filas), 2)
		self.depreciacion_contable = flt(sum(flt(f.depreciacion_contable) for f in filas), 2)
		self.diferencia_depreciacion = flt(self.depreciacion_contable - self.depreciacion_fiscal, 2)

		self.ajustes = [
			a
			for a in self.ajustes
			if not (a.origen == ir2.AUTOMATICO and a.concepto in ir2.CONCEPTOS_CALCULADOS)
		]
		if self.diferencia_depreciacion > 0:
			self._ajuste_automatico(
				ir2.EXCESO_DEPRECIACION,
				self.diferencia_depreciacion,
				_("Depreciación contable mayor que la fiscal"),
			)
		elif self.diferencia_depreciacion < 0:
			self._ajuste_automatico(
				ir2.DEFICIENCIA_DEPRECIACION,
				-self.diferencia_depreciacion,
				_("Depreciación fiscal mayor que la contable"),
			)
		if ajuste_de(ir2.INVENTARIO) > 0:
			self._ajuste_automatico(
				ir2.AJUSTE_INVENTARIO, ajuste_de(ir2.INVENTARIO), _("Ajuste por inflación del inventario")
			)
		for i, a in enumerate(self.ajustes, start=1):
			a.idx = i
			a.tipo = ir2.POSITIVO if a.concepto in ir2.CONCEPTOS_POSITIVOS else ir2.NEGATIVO
		self.total_positivos = flt(sum(flt(a.monto) for a in self.ajustes if a.tipo == ir2.POSITIVO), 2)
		self.total_negativos = flt(sum(flt(a.monto) for a in self.ajustes if a.tipo == ir2.NEGATIVO), 2)

		if self.tasa_isr is None or self.tasa_isr == "":
			self.tasa_isr = ir2.tasa("tasa_isr_juridicas")
		creditos = sum(
			flt(v)
			for v in (
				self.anticipos_pagados,
				self.retenciones_estado,
				self.otros_creditos,
				self.saldo_favor_anterior,
			)
		)
		self.update(
			ir2.liquidar(
				self.beneficio_contable,
				self.total_positivos,
				self.total_negativos,
				self.perdidas_compensables,
				self.tasa_isr,
				creditos,
			)
		)

	def _calcular_edificaciones(self, ajuste_total: float):
		tasa = ir2.tasa_depreciacion(ir2.CATEGORIA_1)
		base_reparto = sum(flt(e.costo_fiscal_inicial) for e in self.edificaciones)
		repartido = 0.0
		con_costo = [e for e in self.edificaciones if flt(e.costo_fiscal_inicial) > 0]
		for e in self.edificaciones:
			if e in con_costo[-1:]:
				e.ajuste_fiscal = flt(ajuste_total - repartido, 2)
			elif e in con_costo:
				e.ajuste_fiscal = flt(ajuste_total * flt(e.costo_fiscal_inicial) / base_reparto, 2)
				repartido += e.ajuste_fiscal
			else:
				e.ajuste_fiscal = 0
			r = ir2.depreciar_edificacion(
				e.costo_fiscal_inicial,
				e.ajuste_fiscal,
				e.adicion,
				e.fecha_adicion,
				e.fecha_retiro,
				self.desde,
				self.hasta,
				tasa,
			)
			e.meses = r.meses
			e.base_depreciable = r.base
			e.depreciacion_fiscal = r.depreciacion
			e.costo_fiscal_final = r.costo_final
