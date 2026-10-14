<template>
	<FrappeUIProvider>
		<!-- El shell usa h-full: necesita la altura de la ventana para fijar el sidebar y el encabezado -->
		<DesktopShell class="h-screen">
			<template #sidebar>
				<Sidebar>
					<SidebarHeader title="RD Compliance" subtitle="ERPNext RD">
						<template #prefix>
							<Logo class="size-7" />
						</template>
					</SidebarHeader>

					<div class="flex-1 overflow-y-auto px-2 py-2">
						<SidebarItem label="Panel" icon="lucide-layout-dashboard" route="/" />

						<SidebarLabel>DGII Fiscal</SidebarLabel>
						<SidebarItem
							label="Secuencias NCF"
							icon="lucide-list-ordered"
							:href="rutaDocumento('Secuencia NCF')"
						/>
						<SidebarItem
							label="Configuración DGII"
							icon="lucide-settings"
							:href="rutaDocumento('Configuracion DGII')"
						/>

						<SidebarLabel>Reportes DGII</SidebarLabel>
						<SidebarItem
							v-for="r in reportes"
							:key="r.reporte"
							:label="r.label"
							icon="lucide-file-text"
							:href="rutaReporte(r.reporte)"
						/>
					</div>

					<div class="px-2 pb-2">
						<SidebarItem label="Ir al escritorio" icon="lucide-arrow-left" href="/desk" />
					</div>
				</Sidebar>
			</template>

			<RouterView />
		</DesktopShell>
	</FrappeUIProvider>
</template>

<script setup>
import { onMounted } from "vue"
import {
	DesktopShell,
	FrappeUIProvider,
	Sidebar,
	SidebarHeader,
	SidebarItem,
	SidebarLabel,
	useColorScheme,
} from "frappe-ui"

import Logo from "@/components/Logo.vue"
import { rutaDocumento, rutaReporte } from "@/utils"

const reportes = [
	{ label: "Formato 606", reporte: "Formato 606 DGII" },
	{ label: "Formato 607", reporte: "Formato 607 DGII" },
	{ label: "Formato 608", reporte: "Formato 608 DGII" },
	{ label: "Formato 609", reporte: "Formato 609 DGII" },
	{ label: "Resumen IT-1", reporte: "Resumen IT-1 DGII" },
	{ label: "Resumen IR-17", reporte: "Resumen IR-17 DGII" },
]

// Mismo tema que el usuario eligió en el escritorio (Light / Dark / Automatic)
const { setColorScheme } = useColorScheme()
onMounted(() => {
	const tema = { Dark: "dark", Light: "light" }[window.desk_theme] || "system"
	setColorScheme(tema)
})
</script>
