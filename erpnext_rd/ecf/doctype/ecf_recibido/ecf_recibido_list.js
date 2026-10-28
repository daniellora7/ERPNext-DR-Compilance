// e-CF recibidos: carga manual del XML que el proveedor envió por correo
frappe.listview_settings["ECF Recibido"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Cargar XML"), () =>
			new frappe.ui.FileUploader({
				restrictions: { allowed_file_types: [".xml"] },
				make_attachments_public: false,
				on_success: (archivo) =>
					frappe
						.call({
							method: "erpnext_rd.ecf.recepcion.cargar_xml",
							args: { file_url: archivo.file_url },
							freeze: true,
						})
						.then(({ message }) => frappe.set_route("Form", "ECF Recibido", message)),
			})
		);
	},
};
