"""La cuenta 210401 «Nómina por Pagar» del catálogo DGII es la cuenta de nómina por pagar de la empresa y
Frappe HR exige que sea de tipo *Payable* para validar una nómina (Payroll Entry). El catálogo la creaba
sin tipo: se corrige en las empresas que ya lo tienen, si la cuenta no tiene movimientos (con movimientos
sin tercero, cambiarle el tipo dejaría asientos inválidos; eso lo decide el contador).
"""

import frappe


def execute():
	for cuenta in frappe.get_all(
		"Account",
		filters={"account_number": "210401", "account_type": ("in", ("", None)), "is_group": 0},
		fields=["name", "company"],
	):
		if not frappe.db.get_value("Company", cuenta.company, "rd_catalogo_dgii"):
			continue
		if frappe.db.exists("GL Entry", {"account": cuenta.name}):
			continue
		frappe.db.set_value("Account", cuenta.name, "account_type", "Payable", update_modified=False)
