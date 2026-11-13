import { createRouter, createWebHistory } from "vue-router"

// `movil`: pantallas para el celular, con MobileShell en vez del shell del escritorio
const routes = [
	{ path: "/", name: "Panel", component: () => import("@/pages/Panel.vue") },
	{ path: "/ecf", name: "Ecf", component: () => import("@/pages/Ecf.vue") },
	{
		path: "/mi-nomina",
		name: "MiNomina",
		component: () => import("@/pages/MiNomina.vue"),
		meta: { portal: true },
	},
	{
		path: "/escanear",
		name: "Escanear",
		component: () => import("@/pages/Escanear.vue"),
		meta: { movil: true },
	},
	{
		path: "/escanear/capturas",
		name: "Capturas",
		component: () => import("@/pages/Capturas.vue"),
		meta: { movil: true },
	},
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

const router = createRouter({
	history: createWebHistory("/rd-compliance"),
	routes,
})

// Quien solo tiene el rol de captura (www/rd_compliance.py) solo ve las pantallas de escanear, y el
// empleado sin roles de contabilidad, solo su portal
router.beforeEach((destino) => {
	if (window.solo_portal && !window.solo_escanear && !destino.meta.portal) return { name: "MiNomina" }
	if (window.solo_escanear && !destino.meta.movil) return { name: "Escanear" }
})

export default router
