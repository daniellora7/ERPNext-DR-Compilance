"""Ventas a clientes de regímenes especiales (Fase 8.4): zonas francas y otros regímenes.

Base (confirmada en los textos de la DGII, 2026-11-11):
- Norma General 05-2019 (vigente desde el 8 de abril de 2019; guía informativa de la DGII): el
  comprobante para Regímenes Especiales (B14, electrónico E44) se usa para vender bienes o servicios
  exentos del ITBIS o el ISC a quienes están acogidos a regímenes especiales por ley, contrato o
  convenio ratificado por el Congreso, cuando el mercado local factura a una zona franca y entre
  zonas francas. La factura no lleva ITBIS ni ISC; el comprador debe tener al día la documentación.
- Consulta DGII G. L. 2817XXX (2022): una zona franca de la Ley 8-90 compra sin ITBIS los bienes y
  servicios para sus operaciones solo si presenta el Carnet de Acreditación de Regímenes Especiales
  actualizado (Código Tributario art. 357, Decreto 293-11 art. 16, Ley 8-90 art. 24 literal g).
- Consulta DGII G. L. 4398XXX (2024): las ventas de mercancías a zonas francas comerciales se tratan
  como exportación (tasa cero de ITBIS, sin ISC) si el suplidor conserva la licencia de la DGA y el
  Formulario Único de Exportación. Lo que la zona franca comercial compra para operar sí lleva ITBIS.
  La consulta no dice qué comprobante usar: aquí no se cambia el comprobante ni los impuestos.
- Empresa que es zona franca industrial (incentivo «Zona franca (Ley 8-90)» vigente en su perfil
  tributario). Según la misma guía, emite el Comprobante para Exportaciones (B16, electrónico E46)
  cuando transfiere bienes al mercado local, sin ITBIS ni ISC, y lo reporta solo en el 607. Se
  propone si todos los artículos son bienes (de inventario o activos fijos); a otra zona franca le
  vende con B14 / E44, como cualquier proveedor.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.impuestos import concepto_de_cuenta

ZONA_FRANCA = "Zona franca (Ley 8-90)"
ZONA_FRANCA_COMERCIAL = "Zona franca comercial"
OTRO_REGIMEN = "Otro régimen especial"
REGIMENES = (ZONA_FRANCA, ZONA_FRANCA_COMERCIAL, OTRO_REGIMEN)
# Los que compran con B14 / E44 sin ITBIS ni ISC
CON_COMPROBANTE_ESPECIAL = (ZONA_FRANCA, OTRO_REGIMEN)
TIPOS_ESPECIALES = ("B14", "E44")
TIPOS_EXPORTACION = ("B16", "E46")


def regimen_del_cliente(customer: str | None) -> frappe._dict:
	if not customer:
		return frappe._dict()
	return (
		frappe.db.get_value(
			"Customer",
			customer,
			["rd_regimen_especial", "rd_carnet_regimen", "rd_carnet_vence"],
			as_dict=True,
		)
		or frappe._dict()
	)


def tipo_especial(serie: str) -> str:
	return "E44" if serie == "E" else "B14"


def _tipo_de_la_venta(doc) -> str | None:
	from erpnext_rd.dgii_fiscal import ncf

	if doc.rd_tipo_comprobante:
		return doc.rd_tipo_comprobante
	if doc.is_return or doc.get("is_debit_note"):
		return None
	return ncf.tipo_por_defecto_venta(doc)


DIAS_AVISO_CARNET = 30
# Un carnet vencido hace más de esto ya no se recuerda: el cliente dejó de comprar o cambió de régimen
DIAS_CARNET_VENCIDO = 90
MESES_CLIENTE_ACTIVO = 12


def carnets_por_vencer(company: str, hoy=None) -> list[frappe._dict]:
	"""Clientes de regímenes especiales que le compraron a la empresa en el último año y cuyo carnet
	vence en DIAS_AVISO_CARNET días o venció hace poco (recordatorio semanal)."""
	from frappe.utils import add_days, add_months

	hoy = getdate(hoy or frappe.utils.today())
	clientes = frappe.get_all(
		"Customer",
		filters={
			"rd_regimen_especial": ("in", CON_COMPROBANTE_ESPECIAL),
			"rd_carnet_vence": (
				"between",
				(add_days(hoy, -DIAS_CARNET_VENCIDO), add_days(hoy, DIAS_AVISO_CARNET)),
			),
		},
		fields=["name", "customer_name", "rd_regimen_especial", "rd_carnet_regimen", "rd_carnet_vence"],
		order_by="rd_carnet_vence asc",
	)
	if not clientes:
		return []
	activos = set(
		frappe.get_all(
			"Sales Invoice",
			filters={
				"company": company,
				"docstatus": 1,
				"customer": ("in", [c.name for c in clientes]),
				"posting_date": (">=", add_months(hoy, -MESES_CLIENTE_ACTIVO)),
			},
			pluck="customer",
			distinct=True,
		)
	)
	return [c for c in clientes if c.name in activos]


def tipo_exportacion(serie: str) -> str:
	return "E46" if serie == "E" else "B16"


def empresa_zona_franca(company: str, fecha=None) -> bool:
	"""La empresa tiene vigente el incentivo de zona franca industrial (Ley 8-90) en su perfil."""
	from erpnext_rd.rd_compliance import perfil

	return any(i.regimen == ZONA_FRANCA for i in perfil.incentivos_vigentes(company, fecha))


def solo_bienes(doc) -> bool:
	"""Todos los artículos son bienes: de inventario o activos fijos (no servicios)."""
	codigos = {f.item_code for f in doc.get("items") or [] if f.item_code}
	if not codigos or len(codigos) < len(doc.get("items") or []):
		return False
	bienes = frappe.get_all(
		"Item",
		filters={"name": ("in", list(codigos))},
		or_filters={"is_stock_item": 1, "is_fixed_asset": 1},
		pluck="name",
	)
	return set(bienes) == codigos


def tipo_zona_franca(doc, serie: str) -> str | None:
	"""Desde ncf.tipo_por_defecto_venta: la zona franca que transfiere bienes al mercado local usa B16 / E46."""
	if empresa_zona_franca(doc.company, doc.get("posting_date")) and solo_bienes(doc):
		return tipo_exportacion(serie)
	return None


def es_venta_exenta(doc) -> bool:
	"""Venta sin ITBIS ni ISC: B14 / E44, o B16 / E46 de una zona franca."""
	tipo = _tipo_de_la_venta(doc)
	return tipo in TIPOS_ESPECIALES or (
		tipo in TIPOS_EXPORTACION and empresa_zona_franca(doc.company, doc.get("posting_date"))
	)


def _es_itbis(fila) -> bool:
	return concepto_de_cuenta(fila.account_head) == cat.ITBIS


def antes_de_validar(doc, method=None):
	"""doc_events before_validate (ventas), antes del ISC: quita las filas de ITBIS de una venta con B14 / E44."""
	from erpnext_rd.dgii_fiscal.ncf import _no_aplica, es_empresa_rd

	if not es_empresa_rd(doc.company) or _no_aplica(doc) or not es_venta_exenta(doc):
		return
	if not doc.get("taxes") and doc.get("taxes_and_charges"):
		doc.append_taxes_from_master()
	quitadas = [f for f in doc.get("taxes") or [] if _es_itbis(f)]
	if not quitadas:
		return
	doc.set("taxes", [f for f in doc.taxes if not _es_itbis(f)])
	for i, fila in enumerate(doc.taxes, start=1):
		fila.idx = i
	doc.taxes_and_charges = None
	frappe.msgprint(
		_("Venta con el comprobante {0}: se quitó el ITBIS (Norma General 05-2019).").format(
			_tipo_de_la_venta(doc)
		),
		indicator="blue",
		alert=True,
	)


def validar_venta(doc, tipo):
	"""Desde ncf.validar_venta: B14 / E44 solo a clientes de regímenes especiales con su carnet vigente;
	B16 / E46 de una zona franca, sin ITBIS ni ISC."""
	if doc.is_return or doc.get("is_debit_note"):
		return
	if tipo.name in TIPOS_EXPORTACION and empresa_zona_franca(doc.company, doc.get("posting_date")):
		_sin_itbis_ni_isc(doc, tipo.name)
		return
	if tipo.name not in TIPOS_ESPECIALES:
		return
	cliente = regimen_del_cliente(doc.customer)
	if cliente.rd_regimen_especial not in CON_COMPROBANTE_ESPECIAL:
		frappe.throw(
			_(
				"El comprobante {0} es para clientes acogidos a regímenes especiales (zonas francas y otros). "
				"Indique el régimen especial en el cliente {1} o use otro comprobante."
			).format(tipo.name, doc.customer),
			title=_("Régimen especial"),
		)
	if not cliente.rd_carnet_regimen:
		frappe.throw(
			_(
				"Registre en el cliente {0} el número del Carnet de Acreditación de Regímenes Especiales (o el "
				"documento que avala la exención) antes de facturar sin ITBIS."
			).format(doc.customer),
			title=_("Régimen especial"),
		)
	fecha = getdate(doc.get("posting_date") or frappe.utils.today())
	if cliente.rd_carnet_vence and getdate(cliente.rd_carnet_vence) < fecha:
		frappe.throw(
			_(
				"El carnet de régimen especial del cliente {0} venció el {1}: pida el carnet actualizado."
			).format(doc.customer, frappe.format(cliente.rd_carnet_vence, "Date")),
			title=_("Régimen especial"),
		)
	_sin_itbis_ni_isc(doc, tipo.name)


def _sin_itbis_ni_isc(doc, tipo: str):
	con_impuesto = [
		f.description or f.account_head
		for f in doc.get("taxes") or []
		if concepto_de_cuenta(f.account_head) in (cat.ITBIS, cat.ISC) and abs(f.tax_amount or 0) > 0.005
	]
	if con_impuesto:
		frappe.throw(
			_("La venta con {0} no lleva ITBIS ni ISC. Quite: {1}.").format(tipo, ", ".join(con_impuesto)),
			title=_("Régimen especial"),
		)
