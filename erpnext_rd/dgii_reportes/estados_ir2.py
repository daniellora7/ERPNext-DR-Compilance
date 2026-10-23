"""Anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2 desde la contabilidad.

Cada cuenta lleva su casilla del IR-2 (`Account.rd_casilla_ir2`). Las del catálogo DGII la traen
asignada por número de cuenta (`casillas_ir2.CASILLAS_CATALOGO`); una cuenta sin casilla toma la de su cuenta
padre más cercana y, si ninguna la tiene, la de su tipo (`casilla_por_tipo`), con un aviso.

- A-1: saldos al cierre. Activos con saldo deudor; depreciación acumulada y provisiones (5.x) como
  deducción; pasivos y patrimonio con saldo acreedor. El resultado de los ejercicios anteriores sin
  asiento de cierre va a 10.4 y el del ejercicio a 10.5 (el asiento de cierre del período no se
  toma en cuenta, así el balance cuadra con o sin él).
- B-1: movimiento del ejercicio sin el asiento de cierre. Ingresos con saldo acreedor; devoluciones
  y descuentos (1.3 y 1.4) se restan; costos y gastos con saldo deudor. La depreciación de las cuentas
  de la casilla 9 se reparte entre 9.1, 9.2 y 9.3 según la categoría fiscal de cada activo. El
  impuesto sobre la renta del ejercicio no entra (la casilla 14 es el beneficio antes del ISR).
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_days, flt, getdate

from erpnext_rd.dgii_reportes.casillas_ir2 import (
	A1,
	B1,
	CASILLAS_CATALOGO,
	DEPRECIACION_B1,
	EXCLUIDO,
	GRUPOS_A1,
	GRUPOS_B1,
	INGRESOS_B1,
	RESTAN_B1,
	casilla_por_tipo,
	codigo,
)


def asignar_casillas(company: str | None = None):
	"""Pone la casilla del catálogo DGII a las cuentas que aún no tienen (por número de cuenta), en
	`company` o en las empresas con el catálogo DGII aplicado."""
	empresas = (
		[company] if company else frappe.get_all("Company", filters={"rd_catalogo_dgii": 1}, pluck="name")
	)
	if not empresas:
		return
	filtros = {
		"company": ("in", empresas),
		"rd_casilla_ir2": ("is", "not set"),
		"account_number": ("in", list(CASILLAS_CATALOGO)),
	}
	for cuenta in frappe.get_all("Account", filters=filtros, fields=["name", "account_number"]):
		frappe.db.set_value(
			"Account",
			cuenta.name,
			"rd_casilla_ir2",
			CASILLAS_CATALOGO[cuenta.account_number],
			update_modified=False,
		)


def casillas_de_cuentas(company: str) -> tuple[dict[str, str | None], list[str]]:
	"""Casilla efectiva de cada cuenta hoja (propia, del padre más cercano o por tipo) y las cuentas
	clasificadas por tipo."""
	cuentas = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=["name", "lft", "rgt", "is_group", "root_type", "account_type", "rd_casilla_ir2"],
		order_by="lft",
	)
	grupos = [c for c in cuentas if c.is_group and c.rd_casilla_ir2]
	resultado, por_tipo = {}, []
	for c in cuentas:
		if c.is_group:
			continue
		valor = c.rd_casilla_ir2
		if not valor:
			# El padre más cercano con casilla: el de lft mayor que contiene a la cuenta
			padres = [g for g in grupos if g.lft < c.lft and g.rgt > c.rgt]
			valor = padres[-1].rd_casilla_ir2 if padres else None
		if not valor:
			valor = casilla_por_tipo(c.root_type, c.account_type)
			por_tipo.append(c.name)
		resultado[c.name] = valor
	return resultado, por_tipo


def _saldos(company: str, desde, hasta) -> dict[str, float]:
	"""Saldo deudor (débito - crédito) por cuenta entre `desde` (sin límite si es None) y `hasta`,
	sin el asiento de cierre del período."""
	gl = frappe.qb.DocType("GL Entry")
	consulta = (
		frappe.qb.from_(gl)
		.select(gl.account, Sum(gl.debit - gl.credit))
		.where(
			(gl.company == company)
			& (gl.is_cancelled == 0)
			& (gl.voucher_type != "Period Closing Voucher")
			& (gl.posting_date <= hasta)
		)
		.groupby(gl.account)
	)
	if desde:
		consulta = consulta.where(gl.posting_date >= desde)
	return {cuenta: flt(saldo) for cuenta, saldo in consulta.run()}


def _depreciacion_por_categoria(company: str, desde, hasta) -> dict[str, float]:
	from erpnext_rd.dgii_reportes import ir2

	total = {}
	categorias = dict(
		frappe.get_all("Asset", filters={"company": company}, fields=["name", "asset_category"], as_list=True)
	)
	for asset, monto in ir2.depreciacion_contable(company, desde, hasta).items():
		categoria = ir2.categoria_fiscal(categorias[asset]) if categorias.get(asset) else None
		cod = DEPRECIACION_B1.get(categoria, "9.3")
		total[cod] = total.get(cod, 0) + monto
	return total


def calcular(company: str, desde, hasta) -> frappe._dict:
	"""Montos por casilla de los anexos A-1 y B-1, sus totales y avisos."""
	desde, hasta = getdate(desde), getdate(hasta)
	casillas, por_tipo = casillas_de_cuentas(company)
	raices = dict(
		frappe.get_all("Account", filters={"company": company}, fields=["name", "root_type"], as_list=True)
	)
	cuentas_por_casilla: dict[tuple, list[str]] = {}

	# B-1: movimiento del ejercicio
	b1: dict[str, float] = {}
	isr = 0.0
	for cuenta, saldo in _saldos(company, desde, hasta).items():
		if raices.get(cuenta) not in ("Income", "Expense"):
			continue
		valor = casillas.get(cuenta)
		if valor == EXCLUIDO:
			isr += saldo
			continue
		par = codigo(valor)
		if not par or par[0] != B1:
			par = codigo(casilla_por_tipo(raices[cuenta], None))
		cod = par[1]
		# Ingresos con saldo acreedor; devoluciones, descuentos, costos y gastos con saldo deudor
		ingreso = cod.split(".")[0] in INGRESOS_B1 and cod not in RESTAN_B1
		b1[cod] = b1.get(cod, 0) + (-saldo if ingreso else saldo)
		cuentas_por_casilla.setdefault((B1, cod), []).append(cuenta)

	# La depreciación contable de la casilla 9.x, por categoría fiscal de los activos
	depreciacion = _depreciacion_por_categoria(company, desde, hasta)
	en_casillas = sum(b1.get(c, 0) for c in DEPRECIACION_B1.values())
	if depreciacion and en_casillas:
		reparto = sum(depreciacion.values())
		for c in DEPRECIACION_B1.values():
			b1.pop(c, None)
		for c, monto in depreciacion.items():
			b1[c] = b1.get(c, 0) + monto
		if flt(en_casillas - reparto, 2):
			b1["9.3"] = b1.get("9.3", 0) + en_casillas - reparto

	totales_b1 = {}
	for g, _d, cs in GRUPOS_B1:
		totales_b1[g] = flt(sum(-b1.get(c, 0) if c in RESTAN_B1 else b1.get(c, 0) for c, _x in cs), 2)
	ingresos = flt(sum(totales_b1[g] for g in INGRESOS_B1), 2)
	costos = flt(sum(v for g, v in totales_b1.items() if g not in INGRESOS_B1), 2)
	totales_b1["4"] = ingresos
	totales_b1["14"] = flt(ingresos - costos, 2)

	# A-1: saldos al cierre
	a1: dict[str, float] = {}
	resultado_anterior = 0.0
	resultado_ejercicio = 0.0
	for cuenta, saldo in _saldos(company, None, hasta).items():
		raiz = raices.get(cuenta)
		if raiz in ("Income", "Expense"):
			continue
		valor = casillas.get(cuenta)
		par = codigo(valor) if valor else None
		if not par or par[0] != A1:
			par = (A1, codigo(casilla_por_tipo(raiz, None))[1])
		cod = par[1]
		grupo = cod.split(".")[0]
		if grupo in ("1", "2", "3", "4"):
			monto = saldo
		else:  # 5 (deducciones del activo), pasivos y patrimonio: saldo acreedor
			monto = -saldo
		a1[cod] = a1.get(cod, 0) + monto
		cuentas_por_casilla.setdefault((A1, cod), []).append(cuenta)

	for cuenta, saldo in _saldos(company, None, add_days(desde, -1)).items():
		if raices.get(cuenta) in ("Income", "Expense"):
			resultado_anterior -= saldo
	for cuenta, saldo in _saldos(company, desde, hasta).items():
		if raices.get(cuenta) in ("Income", "Expense"):
			resultado_ejercicio -= saldo
	a1["10.4"] = a1.get("10.4", 0) + resultado_anterior
	a1["10.5"] = a1.get("10.5", 0) + resultado_ejercicio

	totales_a1 = {g: flt(sum(a1.get(c, 0) for c, _x in cs), 2) for g, _d, cs in GRUPOS_A1}
	totales_a1["6"] = flt(
		totales_a1["1"] + totales_a1["2"] + totales_a1["3"] + totales_a1["4"] - totales_a1["5"], 2
	)
	totales_a1["11"] = flt(totales_a1["7"] + totales_a1["8"] + totales_a1["9"] + totales_a1["10"], 2)

	avisos = []
	if por_tipo:
		avisos.append(
			_("Cuentas sin casilla del IR-2, clasificadas por su tipo: {0}").format(", ".join(por_tipo[:10]))
			+ ("…" if len(por_tipo) > 10 else "")
		)
	if flt(totales_a1["6"] - totales_a1["11"], 2):
		avisos.append(
			_("El balance no cuadra: activos {0}, pasivos y patrimonio {1}.").format(
				frappe.format(totales_a1["6"], "Currency"), frappe.format(totales_a1["11"], "Currency")
			)
		)
	return frappe._dict(
		a1={c: flt(v, 2) for c, v in a1.items()},
		b1={c: flt(v, 2) for c, v in b1.items()},
		totales_a1=totales_a1,
		totales_b1=totales_b1,
		isr=flt(isr, 2),
		cuentas=cuentas_por_casilla,
		avisos=avisos,
	)


def _filas(anexo: str, titulo: str, grupos, montos, totales, cuentas, extra) -> list[dict]:
	filas = [{"casilla": anexo, "descripcion": titulo, "negrita": 1}]
	for g, descripcion, casillas in grupos:
		filas.append(
			{"casilla": g, "descripcion": descripcion, "monto": totales[g], "negrita": 1, "indent": 0}
		)
		if len(casillas) == 1 and casillas[0][0] == g:
			filas[-1]["cuentas"] = ", ".join(cuentas.get((anexo, g), []))
			continue
		for c, d in casillas:
			filas.append(
				{
					"casilla": c,
					"descripcion": d,
					"monto": montos.get(c, 0),
					"cuentas": ", ".join(cuentas.get((anexo, c), [])),
					"indent": 1,
				}
			)
		filas.extend(extra.get(g, []))
	return filas


def reporte(filters: dict | None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "casilla", "label": _("Casilla"), "fieldtype": "Data", "width": 80},
		{"fieldname": "descripcion", "label": _("Descripción"), "fieldtype": "Data", "width": 420},
		{"fieldname": "monto", "label": _("Monto"), "fieldtype": "Currency", "width": 170},
		{"fieldname": "cuentas", "label": _("Cuentas"), "fieldtype": "Data", "width": 420},
	]
	if not (filters.company and filters.desde and filters.hasta):
		return columnas, []
	r = calcular(filters.company, filters.desde, filters.hasta)
	total_activos = {
		"casilla": "6",
		"descripcion": _("Total activos"),
		"monto": r.totales_a1["6"],
		"negrita": 1,
	}
	filas = _filas(
		A1,
		_("Anexo A-1: balance general al cierre"),
		GRUPOS_A1,
		r.a1,
		r.totales_a1,
		r.cuentas,
		{"5": [total_activos]},
	)
	filas.append(
		{
			"casilla": "11",
			"descripcion": _("Total pasivos y patrimonio"),
			"monto": r.totales_a1["11"],
			"negrita": 1,
		}
	)
	filas.append({})
	total_ingresos = {
		"casilla": "4",
		"descripcion": _("Total ingresos"),
		"monto": r.totales_b1["4"],
		"negrita": 1,
	}
	filas += _filas(
		B1,
		_("Anexo B-1: estado de resultados del ejercicio"),
		GRUPOS_B1,
		r.b1,
		r.totales_b1,
		r.cuentas,
		{"3": [total_ingresos]},
	)
	filas.append(
		{
			"casilla": "14",
			"descripcion": _("Beneficio (pérdida) antes del impuesto sobre la renta"),
			"monto": r.totales_b1["14"],
			"negrita": 1,
		}
	)
	resumen = [
		{
			"label": _("Total activos"),
			"value": r.totales_a1["6"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Pasivos y patrimonio"),
			"value": r.totales_a1["11"],
			"datatype": "Currency",
			"indicator": "Blue" if not flt(r.totales_a1["6"] - r.totales_a1["11"], 2) else "Red",
		},
		{
			"label": _("Beneficio antes del ISR"),
			"value": r.totales_b1["14"],
			"datatype": "Currency",
			"indicator": "Green" if r.totales_b1["14"] >= 0 else "Red",
		},
	]
	mensaje = " ".join(
		[
			_(
				"Saldos por casilla de los anexos A-1 y B-1 del IR-2, según la casilla de cada cuenta "
				"(campo «Casilla del IR-2» del catálogo de cuentas). Sin el asiento de cierre del período."
			),
			*r.avisos,
		]
	)
	return columnas, filas, mensaje, None, resumen
