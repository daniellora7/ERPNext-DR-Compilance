# Lineamientos de diseño de Frappe

Resumen de los lineamientos oficiales de Frappe (consultados el 2026-10-15) para revisar que RD Compliance y Nómina RD los cumplan. Fuentes: [frappe.io/design](https://frappe.io/design), [Espresso](https://frappe.io/design/espresso), [Voz de marca](https://frappe.io/design/voice) y la documentación de [frappe-ui](https://ui.frappe.io/docs/getting-started) (tokens y componentes). Figma: [Espresso by Frappe](https://www.figma.com/community/file/1407648399328528443/espresso-by-frappe).

## Principios

1. **El diseño es el texto**: cada etiqueta y botón dice exactamente lo que hace.
2. **Mínimo**: sin elementos, bordes ni clics de más.
3. **Dejar trabajar**: la interfaz pasa a segundo plano mientras el usuario trabaja.
4. **Jerarquía**: el sistema se divide en piezas para que el usuario llegue a su objetivo sin pensar en el cómo.
5. **Guiar sin abrumar**: una sola acción principal a la vez; si ninguna gana claramente, no forzarla.
6. **Contexto, no ruido**: avisos, enlaces y ajustes junto a donde se necesitan.
7. **Consistencia** entre productos: mismas decisiones, mismos componentes.

## Texto (voz)

- Frases cortas y directas, sin relleno ni palabras exageradas («sin fricciones», «increíble»).
- Títulos en **mayúscula solo al inicio** («Archivo de novedades», no «Archivo De Novedades»).
- Tono amable pero no informal; pocas exclamaciones y emojis.
- Fechas completas sin ordinales.
- Texto alineado a la izquierda; títulos claros en cada página; pensar también en el móvil.

## Color (tokens de frappe-ui)

| Uso | Token |
|---|---|
| Fondo de página, tarjetas, menús | `surface-base` |
| Fondos suaves, hover, presionado | `surface-gray-2`, `surface-gray-3` |
| Texto principal | `ink-gray-8` |
| Texto secundario (ayudas, fechas) | `ink-gray-5` |
| Bordes y divisores | `outline-gray-1`, `outline-gray-2` |
| Estados | `surface-<color>-2` + `ink-<color>-7` (p. ej. verde para «aprobado») |

- `surface` va con `bg-`, `ink` con `text-`, `outline` con `border-`. En CSS: `var(--ink-gray-8)`, etc.
- **Sin `dark:`**: los tokens cambian solos con `data-theme="dark"`.
- La paleta fija (`gray-500`, etc.) solo para colores que no deben cambiar con el tema; **nunca hex** en la interfaz.
- Transparencias: tokens `alpha` (no `/50` sobre ellos).

## Tipografía

- Inter. Peso con sufijo en la clase de tamaño (`text-base-medium`, `text-lg-semibold`), no `font-medium` solo.
- `text-base` (14px) para la mayoría de controles; `text-sm` (13px) para texto menor.
- Texto de varias líneas: `text-p-*`. Una sola línea en caja de alto fijo: `leading-tighter`.
- Títulos: `text-2xl`–`text-4xl` según nivel.

## Forma y elevación

- Radios numéricos: `rounded-4` (8px) botones, campos y elementos de menú; `rounded-6` (12px) menús y tarjetas; `rounded-7` (16px) diálogos; `rounded-full` insignias y avatares. **No** `rounded-lg/md/sm` ni `rounded` solo.
- Sombras siempre con su superficie de elevación: `shadow-sm` + `surface-elevation-3` (pestaña o elemento activo), `shadow-xl` + `surface-elevation-1` (diálogos), `shadow-2xl` + `surface-elevation-2` (menús). En oscuro la sombra sola no se ve.

## Íconos

- **Lucide** (`lucide-<nombre>`), del color del texto (`text-ink-*`) y tamaño `size-4` / `size-5`.
- Nombres de clase completos en el código (Tailwind no ve los armados en tiempo de ejecución).

## Componentes

Usar los de frappe-ui antes que HTML propio: `Button`, `TextInput`, `Select`, `Dialog`, `Dropdown`, `Badge`, `Tabs`, `Toast`, `Alert`, `PageHeader`, `Sidebar`, `DesktopShell`, `Skeleton`, `LoadingText`, etc. Cada uno trae sus estados (normal, hover, foco, activo, deshabilitado, cargando).

## Lista de revisión (RD Compliance y Nómina RD)

- [ ] Etiquetas y botones dicen exactamente lo que hacen; títulos con mayúscula solo al inicio.
- [ ] Una acción principal por pantalla o diálogo.
- [ ] Sin hex ni clases de Bootstrap: solo tokens `surface` / `ink` / `outline` (también en HTML de reportes y mensajes; se exceptúan los formatos de impresión).
- [ ] Texto principal `ink-gray-8`, secundario `ink-gray-5`; avisos y errores con tokens de color.
- [ ] Radios numéricos y sombras con su superficie de elevación.
- [ ] Íconos Lucide, coherentes con el dock de Frappe v16.52 (íconos de un solo color).
- [ ] Componentes de frappe-ui en el panel; tipografía con sufijo de peso.
- [ ] Revisado en claro y oscuro, y en móvil.
- [ ] Avisos y enlaces junto al dato que los motiva, sin saturar la pantalla.
