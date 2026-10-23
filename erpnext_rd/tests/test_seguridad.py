import frappe
from frappe.tests import IntegrationTestCase

# Métodos whitelisted que escriben o envían a la DGII: solo POST, para que Frappe exija el token CSRF
# (una petición GET no lo revisa y se podría disparar desde una imagen o un enlace de otro sitio).
SOLO_POST = [
	"erpnext_rd.dgii_fiscal.consulta_ncf.verificar_factura",
	"erpnext_rd.dgii_fiscal.tasa_bcrd.actualizar_ahora",
	"erpnext_rd.dgii_reportes.ir2.traer_datos",
	"erpnext_rd.dgii_reportes.ir2.crear_base_anticipos",
	"erpnext_rd.ecf.certificacion.generar",
	"erpnext_rd.ecf.certificacion.enviar",
	"erpnext_rd.ecf.emision.emitir",
	"erpnext_rd.ecf.emision.reenviar",
	"erpnext_rd.ecf.emision.entregar",
	"erpnext_rd.ecf.recepcion.aprobar",
	"erpnext_rd.ecf.recepcion.reenviar_aprobacion",
	"erpnext_rd.nomina_rd.regalia.crear_regalias",
	"erpnext_rd.nomina_rd.subsidios.salario_desde_nomina",
	"erpnext_rd.padron_rnc.padron.encolar_sincronizacion",
	"erpnext_rd.rd_compliance.perfil.guardar",
	"erpnext_rd.rd_compliance.perfil.crear_anio_fiscal",
]


class TestSeguridad(IntegrationTestCase):
	def test_metodos_que_escriben_solo_por_post(self):
		for ruta in SOLO_POST:
			funcion = frappe.get_attr(ruta)
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(funcion), ["POST"], ruta)

	def test_metodos_de_controlador_que_escriben_solo_por_post(self):
		# frappe.get_attr no resuelve métodos de clase: se toman de la clase importada
		from erpnext_rd.ecf.doctype.anulacion_encf.anulacion_encf import AnulacionENCF

		for funcion in [AnulacionENCF.enviar_dgii]:
			self.assertEqual(
				frappe.allowed_http_methods_for_whitelisted_func.get(funcion), ["POST"], funcion.__qualname__
			)
