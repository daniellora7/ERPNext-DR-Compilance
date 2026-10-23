<!-- Tarjeta de una declaración o formato: NumberCard de frappe-ui (título, cifra y plazo) dentro de
     la misma superficie que los widgets numéricos del escritorio v16 (radio 12px, borde outline-gray-2 para que se distinga en el tema claro),
     con el detalle y el enlace al reporte debajo. -->
<template>
	<div class="flex flex-col rounded-6 border border-outline-gray-2 bg-surface-base">
		<NumberCard
			:card="false"
			class="px-4 pt-3.5"
			:title="subtitulo ? `${titulo} · ${subtitulo}` : titulo"
			:value="valor"
			:delta-caption="etiquetaValor"
			:loading="cargando"
		>
			<template v-if="vence" #actions>
				<Plazo :vence="vence" />
			</template>
		</NumberCard>

		<div class="flex-1 px-4 pt-3 pb-4">
			<dl v-if="detalle?.length" class="space-y-1.5">
				<div v-for="d in detalle" :key="d.label" class="flex justify-between gap-3 text-sm">
					<dt class="text-ink-gray-5">{{ d.label }}</dt>
					<dd class="tabular-nums" :class="d.clase || 'text-ink-gray-7'">{{ d.valor }}</dd>
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
import { NumberCard } from "frappe-ui/charts"
import Plazo from "@/components/Plazo.vue"
import { __ } from "@/translation"

defineProps({
	titulo: { type: String, required: true },
	subtitulo: String,
	vence: { type: String, default: null },
	valor: { type: String, default: null },
	etiquetaValor: String,
	detalle: Array,
	enlace: String,
	textoEnlace: { type: String, default: () => __("Abrir reporte") },
	cargando: Boolean,
})
</script>
