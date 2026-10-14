<template>
	<FrappeUIProvider>
		<!-- Dentro del escritorio la navegación la da el sidebar del escritorio -->
		<div v-if="embebido" class="h-screen overflow-y-auto">
			<RouterView />
		</div>

		<!-- El shell usa h-full: necesita la altura de la ventana para fijar el sidebar y el encabezado -->
		<DesktopShell v-else class="h-screen">
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
import {
	DesktopShell,
	FrappeUIProvider,
	Sidebar,
	SidebarHeader,
	SidebarItem,
	SidebarLabel,
} from "frappe-ui"

import Logo from "@/components/Logo.vue"
import { embebido, rutaDocumento, rutaReporte } from "@/utils"

const reportes = [
	{ label: "Formato 606", reporte: "Formato 606 DGII" },
	{ label: "Formato 607", reporte: "Formato 607 DGII" },
	{ label: "Formato 608", reporte: "Formato 608 DGII" },
	{ label: "Formato 609", reporte: "Formato 609 DGII" },
	{ label: "Resumen IT-1", reporte: "Resumen IT-1 DGII" },
	{ label: "Resumen IR-17", reporte: "Resumen IR-17 DGII" },
]
</script>
