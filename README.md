# ERPNext RD

Localización de **República Dominicana** para ERPNext v16 y Frappe HR, libre y de código abierto (GPL-3.0). Adapta lo que ya traen ERPNext y Frappe HR a las normas dominicanas (DGII, TSS, Código de Trabajo) en vez de reemplazarlo: agrega campos, configuraciones y cálculos sobre sus propios documentos.

## Del lado de ERPNext: cumplimiento fiscal (dock de ERPNext → *RD Compliance*)

- **DGII Fiscal**: tipos de comprobante (B01–B17, E31–E47), secuencias NCF sin duplicados, NCF en ventas, compras y POS, validación de RNC y Cédula, catálogo de cuentas DGII (NIIF PYMES) con plantillas de ITBIS y retenciones, formatos de impresión fiscales.
- **DGII Reportes**: formatos 606, 607, 608 y 609 con descarga del TXT oficial, y resúmenes de apoyo para el IT-1 y el IR-17.
- **Padrón RNC**: padrón de contribuyentes de la DGII (cada día a las 2:00 a. m. revisa si la DGII publicó uno nuevo y solo entonces lo descarga) y autocompletado de la razón social.
- **Panel RD Compliance** (*RD Compliance → Panel de cumplimiento*, dentro del escritorio; también en `/rd-compliance`): en una pantalla, los plazos y montos del 606, 607, 608, 609, IT-1 e IR-17 del mes, las secuencias NCF por agotarse o vencer y los registros con observaciones antes de enviarlos. Hecho con [frappe-ui](https://ui.frappe.io), el mismo estilo del escritorio de Frappe v16.
- **Feriados de RD**: una lista de feriados de ERPNext, *Feriados RD*, con los feriados dominicanos y sus traslados según la Ley 139-97 (los toma de la misma librería que usa el botón "Agregar feriados locales" de ERPNext) y el domingo como día de descanso. Se crea sola, se extiende cada año hasta el 31 de diciembre del año siguiente y queda como lista por defecto de las empresas RD que no tengan otra. Lo que edites a mano (por ejemplo, un decreto que mueva un feriado) se respeta.
- **e-CF** (en desarrollo): facturación electrónica directa con la DGII.

## Del lado de Frappe HR: Nómina RD (dock de Frappe HR → *Nómina RD*)

Frappe HR es opcional. Cuando está instalado, la app lo adapta a la República Dominicana usando sus propios documentos (recibo de nómina, estructura salarial, Gratuity, liquidación final). Todo queda en una entrada **Nómina RD** del dock de Frappe HR, junto a Payroll, Leaves, etc.:

- **Recibo de nómina** (*Salary Slip* de Frappe HR): calcula solo las deducciones de ley del empleado (AFP, SFS) y los aportes del empleador (AFP, SFS, SRL, INFOTEP) con los topes en salarios mínimos de la TSS, y la retención de ISR de asalariados con la escala anual, proyectada al año. Los componentes salariales de ley se crean solos, con sus cuentas del catálogo DGII. En cada componente se indica si cotiza a la TSS (por ejemplo, la regalía y los bonos no cotizan).
- **Regalía pascual** (salario de Navidad, art. 219): la duodécima parte de los salarios ordinarios del año, exenta de ISR y TSS.
- **Prestaciones laborales** sobre el *Gratuity* de Frappe HR: las reglas **Preaviso RD** (art. 76) y **Cesantía RD** (art. 80) calculan los días según el tiempo de servicio (los tramos de 3 a 6 meses y de 6 a 12 meses, y 21 o 23 días por año) y el salario diario (salario promedio del último año, art. 85, entre 23.83). El documento muestra los meses de servicio, los días y el salario usado. El asiento, el pago (por nómina o por banco) y la **liquidación final** (*Full and Final Statement*) siguen siendo los de Frappe HR.
- **Reclamos de gastos**: los tipos de reclamo usan la cuenta de gasto del catálogo DGII.
- **Configuración Nómina RD**: tasas, topes, escala del ISR, tramos de preaviso y cesantía, días por mes y la lista de feriados, todo editable porque cambia por ley o resolución.

### Si Frappe HR se instala o se quita después

- **Frappe HR ya instalado al instalar ERPNext RD**: la Nómina RD queda activa desde el principio.
- **Frappe HR instalado después**: al terminar su instalación, ERPNext RD activa la Nómina RD sola, sin pasos en la consola. Crea los campos en sus documentos, los componentes de ley con sus cuentas, las reglas de prestaciones y la entrada en el dock.
- **Frappe HR desinstalado**: se retiran los campos que la app había agregado a sus documentos y la entrada del dock. La parte fiscal sigue funcionando igual.
- **Sin Frappe HR**: ERPNext RD funciona completa en lo fiscal. Los feriados también, porque la lista de feriados es de ERPNext.

La app no modifica el código de ERPNext ni de Frappe HR: todo va por hooks, campos personalizados y configuraciones, así que se pueden actualizar sin conflictos.

Toda la lógica (fiscal y de nómina) se aplica solo a las empresas con país *Dominican Republic*, así que la app convive con empresas de otros países en el mismo sitio.

## Instalación

### Frappe Cloud

Próximamente en el Marketplace de Frappe Cloud.

### Bench

```bash
bench get-app https://github.com/daniellora7/ERPNext-DR-Compilance --branch develop
bench --site <sitio> install-app erpnext_rd
```

Requiere ERPNext v16. Frappe HR es opcional: si está instalado (antes o después), se activa la Nómina RD.

### Docker

El repositorio trae una imagen y un stack Compose con Frappe + ERPNext + Frappe HR + ERPNext RD en un solo sitio y una sola base MariaDB (ver `deploy/`).

```bash
cp deploy/.env.example deploy/.env   # cambiar contraseñas
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f create-site
```

Abrir http://localhost:8090 con el usuario `Administrator` y la contraseña `ADMIN_PASSWORD` del `.env`.

## Estructura

| Ruta | Contenido |
|---|---|
| `erpnext_rd/` | La app Frappe (módulos DGII Fiscal, DGII Reportes, Padron RNC, ECF y el menú RD Compliance del lado de ERPNext; Nomina RD del lado de Frappe HR) |
| `pyproject.toml` | Paquete de la app (lo usan `bench get-app` y Frappe Cloud) |
| `frontend/` | Panel RD Compliance (Vue 3 + frappe-ui); `bench build` lo compila |
| `deploy/` | Imagen Docker, stack Compose y script de CI |
| `docs/PLAN.md` | Plan, fases y estado del proyecto |

## Desarrollo

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.dev.yaml --env-file deploy/.env up -d
DEV=1 deploy/ci/run-tests.sh
```

`compose.dev.yaml` monta el paquete `erpnext_rd/` dentro de los contenedores, así no hace falta reconstruir la imagen. Ramas: `main` = estable, `develop` = integración, `feature/*` para trabajo nuevo.

## Licencia

GPL-3.0. Ver [LICENSE](LICENSE).
