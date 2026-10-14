// Panel RD Compliance dentro del escritorio (/desk/panel-cumplimiento). El panel es la app frappe-ui
// de /rd-compliance; aquí se muestra en un iframe del mismo sitio, sin su propio sidebar (usa el del
// escritorio), y sus enlaces navegan el escritorio en la misma ventana (ver frontend/src/main.js).
frappe.pages["panel-cumplimiento"].on_page_load = (wrapper) => {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Panel de cumplimiento"), single_column: true });

	// El panel trae su propio encabezado (título, empresa y período). En el móvil se deja el del
	// escritorio, que tiene el botón del menú.
	$(wrapper).append(
		"<style>@media (min-width: 768px) { #page-panel-cumplimiento .page-head { display: none; } }</style>"
	);

	const iframe = document.createElement("iframe");
	iframe.src = "/rd-compliance";
	iframe.title = __("Panel de cumplimiento");
	iframe.style.cssText = "display:block;width:100%;border:0;";
	$(wrapper).find(".layout-main-section").empty().append(iframe);

	// Ocupa el alto visible del escritorio debajo de la barra superior
	const ajustar = () => {
		const arriba = iframe.getBoundingClientRect().top + window.scrollY;
		iframe.style.height = `${Math.max(window.innerHeight - arriba, 400)}px`;
	};
	$(window).on("resize", frappe.utils.debounce(ajustar, 100));
	wrapper.ajustar_panel = ajustar;
};

frappe.pages["panel-cumplimiento"].on_page_show = (wrapper) => {
	wrapper.ajustar_panel?.();
};
