import { createRouter, createWebHistory } from "vue-router"

const routes = [
	{ path: "/", name: "Panel", component: () => import("@/pages/Panel.vue") },
	{ path: "/:pathMatch(.*)*", redirect: "/" },
]

export default createRouter({
	history: createWebHistory("/rd-compliance"),
	routes,
})
