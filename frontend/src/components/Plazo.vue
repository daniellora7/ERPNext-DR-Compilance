<!-- Insignia con el plazo de presentación: rojo a 5 días o menos, ámbar a 10 o menos -->
<template>
	<Tooltip :text="__('Vence el {0}', [formatoFecha(vence)])">
		<Badge :theme="tema" variant="subtle" :label="texto" />
	</Tooltip>
</template>

<script setup>
import { computed } from "vue"
import { Badge, Tooltip } from "frappe-ui"
import { __ } from "@/translation"
import { diasHasta, formatoFecha } from "@/utils"

const props = defineProps({ vence: { type: String, required: true } })

const dias = computed(() => diasHasta(props.vence))
const tema = computed(() => {
	if (dias.value < 0) return "gray"
	if (dias.value <= 5) return "red"
	if (dias.value <= 10) return "amber"
	return "gray"
})
const texto = computed(() => {
	if (dias.value < 0) return __("Plazo vencido")
	if (dias.value === 0) return __("Vence hoy")
	if (dias.value === 1) return __("Vence mañana")
	return __("Vence en {0} días", [dias.value])
})
</script>
