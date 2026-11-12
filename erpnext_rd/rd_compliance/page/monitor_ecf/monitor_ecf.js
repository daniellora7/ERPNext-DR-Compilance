// Monitor de e-CF dentro del escritorio (/desk/monitor-ecf): la pantalla /rd-compliance/ecf de la app
// frappe-ui en un iframe, igual que el Panel de cumplimiento (ver panel_cumplimiento.js).
frappe.pages["monitor-ecf"].on_page_load = (wrapper) => {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Monitor de e-CF"), single_column: true });

	// El panel trae su propio encabezado (título, empresa y período). En el móvil se deja el del
	// escritorio, que tiene el botón del menú.
	$(wrapper).append(
		"<style>@media (min-width: 768px) { #page-monitor-ecf .page-head { display: none; } }</style>"
	);

	const iframe = document.createElement("iframe");
	iframe.src = "/rd-compliance/ecf";
	iframe.title = __("Monitor de e-CF");
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

frappe.pages["monitor-ecf"].on_page_show = (wrapper) => {
	wrapper.ajustar_panel?.();
};
