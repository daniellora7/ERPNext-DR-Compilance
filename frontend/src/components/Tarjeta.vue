<!-- Tarjeta de una declaración o formato: título, plazo, monto principal y detalle -->
<template>
	<div class="flex flex-col rounded-lg border border-outline-gray-2 bg-surface-base">
		<div class="flex items-start justify-between gap-2 px-4 pt-4">
			<div class="min-w-0">
				<div class="text-base-medium text-ink-gray-8">{{ titulo }}</div>
				<div v-if="subtitulo" class="mt-1 text-sm text-ink-gray-5">{{ subtitulo }}</div>
			</div>
			<Plazo v-if="vence" :vence="vence" />
		</div>

		<div class="flex-1 px-4 pt-3 pb-4">
			<div v-if="valor !== undefined" class="text-2xl-semibold tabular-nums text-ink-gray-8">
				{{ valor }}
			</div>
			<div v-if="etiquetaValor" class="mt-1 text-sm text-ink-gray-5">{{ etiquetaValor }}</div>
			<dl v-if="detalle?.length" class="mt-3 space-y-1.5">
				<div v-for="d in detalle" :key="d.label" class="flex justify-between gap-3 text-sm">
					<dt class="text-ink-gray-6">{{ d.label }}</dt>
					<dd class="tabular-nums" :class="d.clase || 'text-ink-gray-8'">{{ d.valor }}</dd>
				</div>
			</dl>
			<slot />
		</div>

		<div v-if="enlace" class="border-t border-outline-gray-1 px-2 py-1.5">
			<Button variant="ghost" :href="enlace" icon-right="lucide-arrow-up-right" :label="textoEnlace" />
		</div>
	</div>
</template>

<script setup>
import { Button } from "frappe-ui"
import Plazo from "@/components/Plazo.vue"

defineProps({
	titulo: { type: String, required: true },
	subtitulo: String,
	vence: { type: String, default: null },
	valor: { type: String, default: undefined },
	etiquetaValor: String,
	detalle: Array,
	enlace: String,
	textoEnlace: { type: String, default: "Abrir reporte" },
})
</script>
