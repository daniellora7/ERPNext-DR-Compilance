# CLAUDE.md

Guía para trabajar en este repositorio. El usuario se comunica en español: responder en español.

## Qué es

**ERPNext RD**: ERPNext + Frappe HR (HRMS) + app propia `erpnext_rd` con la localización de República Dominicana (NCF, e-CF directo con la DGII, reportes 606/607/608/609, padrón RNC y nómina RD). Se corre en Docker local y después se despliega en Dokploy.

Plan completo, fases y estado: `docs/PLAN.md` (mantenerlo actualizado al avanzar cada fase).

## Versiones fijadas

| Componente | Versión | Dónde se fija |
|---|---|---|
| Frappe | v16.51.1 | `FRAPPE_BRANCH` en `deploy/Containerfile` |
| ERPNext | v16.50.0 | `deploy/apps.json` |
| HRMS | v16.50.0 | `deploy/apps.json` |
| MariaDB | 11.8 | `deploy/compose.yaml` |
| Python (en imagen) | 3.14 | imagen `frappe/build:version-16` |

## Reglas de arquitectura

- **Una sola instancia = un solo sitio Frappe = una sola base de datos MariaDB.** ERPNext, HRMS y `erpnext_rd` se instalan en el mismo sitio. Varias empresas = varias *Company* en ese sitio. No crear sitios ni bases de datos adicionales.
- **MariaDB, no PostgreSQL** (es la base oficial y probada de ERPNext/HRMS).
- **No hacer fork ni modificar** el código de Frappe, ERPNext o HRMS. Toda personalización va en la app `erpnext_rd` mediante DocTypes propios, `hooks.py` (`doc_events`, `scheduler_events`, `override_*`), Custom Fields y Property Setters exportados como fixtures, y patches.
- Tasas y topes que cambian por ley (TSS, ISR, INFOTEP, etc.) van en DocTypes de configuración editables, nunca hardcodeados.
- Solo copiar código de terceros con licencia compatible (GPL-3, LGPL-3 o MIT). Repos sin licencia solo sirven de referencia. La app es GPL-3.0.

## Estructura

```
pyproject.toml                 Paquete de la app (en la raíz: así lo esperan bench get-app y Frappe Cloud)
package.json                   Script build que `bench build` corre para compilar frontend/
frontend/                      Panel RD Compliance (Vue 3 + frappe-ui 1.x, Vite, Tailwind 3) en /rd-compliance
erpnext_rd/                    App Frappe propia
  hooks.py                   Hooks de la app (required_apps = erpnext)
  modules.txt                Módulos: ERPNext RD, DGII Fiscal, ECF, DGII Reportes, Padron RNC, Nomina RD, RD Compliance (navegación)
  dgii_fiscal/               NCF, tipos de comprobante, campos fiscales
  ecf/                       e-CF: XML, firma, envío/consulta DGII, recepción
  dgii_reportes/             606, 607, 608, 609, apoyo IT-1 / IR-17
  padron_rnc/                Padrón RNC/Cédula y validaciones
  nomina_rd/                 TSS, ISR, INFOTEP, regalía, IR-3, archivo SUIR
  rd_compliance/             Módulo de navegación: sidebar único con todas las secciones; panel.py = API del panel
  www/rd_compliance.py       Página del panel (el HTML www/rd-compliance.html lo genera el build, no se versiona)
  dock/                      Ícono de la app en el dock de Frappe v16
  fixtures/                  Custom Fields / Property Setters exportados
  patches.txt, patches/      Migraciones de datos
  tests/                     Tests de la app
deploy/
  apps.json                    Apps oficiales y sus tags
  Containerfile                Imagen (basada en frappe_docker layered, MIT)
  compose.yaml                 Stack completo
  .env.example                 Variables (copiar a deploy/.env, que NO se versiona)
  resources/                   entrypoint y start.sh de frappe_docker
```

## Comandos

Todos desde la raíz del repo. Atajo: `C="docker compose -f deploy/compose.yaml --env-file deploy/.env"`.

```bash
# Construir imagen (tarda ~15 min la primera vez)
docker build -f deploy/Containerfile -t erpnext-rd:local .

# Levantar / detener
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d
docker compose -f deploy/compose.yaml --env-file deploy/.env down

# DESARROLLO (recomendado): monta el paquete erpnext_rd/ dentro de los contenedores, sin rebuild
docker compose -f deploy/compose.yaml -f deploy/compose.dev.yaml --env-file deploy/.env up -d
#   cambios Python   -> docker restart deploy-backend-1 deploy-queue-short-1 deploy-queue-long-1 deploy-scheduler-1
#   DocTypes/campos  -> docker exec deploy-backend-1 bench --site erp.localhost migrate

# Imagen de producción con el código actual (create-site corre migrate si el sitio existe)
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build

# Bench dentro del contenedor
docker exec deploy-backend-1 bench --site erp.localhost list-apps
docker exec deploy-backend-1 bench --site erp.localhost migrate
docker exec deploy-backend-1 bench --site erp.localhost console
docker exec deploy-backend-1 bench --site erp.localhost mariadb

# Tests de la app
docker exec deploy-backend-1 bench --site erp.localhost set-config allow_tests true
docker exec deploy-backend-1 bench --site erp.localhost run-tests --app erpnext_rd

# Panel RD Compliance (frontend/): compilar sin Node en Windows, en un contenedor desechable.
# Escribe erpnext_rd/public/frontend y erpnext_rd/www/rd-compliance.html (montados en el stack dev)
MSYS_NO_PATHCONV=1 docker run --rm -u root --entrypoint bash -v "$PWD:/work" -v erpnext-rd-frontend-nm:/work/frontend/node_modules -w /work/frontend erpnext-rd:local -c "yarn install --frozen-lockfile && yarn build"

# Logs
docker logs -f deploy-backend-1
docker logs deploy-create-site-1
```

- URL local: http://localhost:8090 (el 8080 lo usa otro proyecto del usuario, `plastidel-dev-api`; no tocarlo).
- Sitio: `erp.localhost`. Usuario `Administrator`; la contraseña es `ADMIN_PASSWORD` en `deploy/.env`. No repetir contraseñas en el chat.
- Los volúmenes Docker (`deploy_sites`, `deploy_db-data`) guardan los datos; `down -v` los borra. No usarlo sin confirmación del usuario.

## Notas técnicas

- La imagen copia `erpnext_rd` dentro; para desarrollar usar `deploy/compose.dev.yaml`, que monta el código del repo.
- Campos personalizados y catálogos se crean por código en `erpnext_rd/install.py` (`after_install` / `after_migrate`, idempotente), no con fixtures exportados.
- DocTypes nuevos: se escriben como JSON en `<modulo>/doctype/<nombre>/` (ver los existentes) y se aplican con `migrate`.
- Catálogo de cuentas DGII: `dgii_fiscal/catalogo_cuentas.py`. Se aplica **por empresa** y solo a empresas con país *Dominican Republic* sin movimientos: en `after_install`/`after_migrate` y en `Company.on_update` (después de que ERPNext crea el catálogo estándar, se reemplaza). Se desactiva con *Configuracion DGII → aplicar_catalogo_cuentas*. La empresa queda marcada con `rd_catalogo_dgii`. Empresas de otros países no se tocan.
- **Multiempresa / multipaís:** toda la lógica fiscal DGII (NCF, validación de RNC, catálogo, reportes) se limita a empresas con país *Dominican Republic* (`ncf.es_empresa_rd`). Proveedores y empresas de otro país conservan su ID fiscal sin validar. Mantener esta regla en todo lo nuevo.
- Reportes DGII: `dgii_reportes/datos.py` (registros), `formatos.py` (columnas oficiales, TXT, `descargar_txt`), Script Reports en `dgii_reportes/report/formato_6xx_dgii/`. Los impuestos se clasifican por el campo `rd_concepto_fiscal` de la cuenta (`dgii_fiscal/impuestos.py`). Los resúmenes IT-1 / IR-17 están en `dgii_reportes/declaraciones.py` y reutilizan las filas del 606/607/609 (columnas internas `_reinformado`, `_nota_credito`). Ojo: Frappe nombra la carpeta de un reporte con el nombre *scrubbed* (`Resumen IT-1 DGII` → `resumen_it_1_dgii`).
- **Navegación (UI):** todo se agrupa en un solo módulo **RD Compliance** (`rd_compliance/`). Sidebar en `rd_compliance/sidebar/rd_compliance/rd_compliance.json` (secciones `Section Break` con `indent: 1` y enlaces `Link` con `child: 1`); ícono del dock en `erpnext_rd/dock/erpnext_rd/erpnext_rd.json` (`mount_on: erpnext`); ícono duotono `rd-compliance-duotone` en `public/icons/erpnext-rd-icons.svg` (`app_include_icons`). `code_only_modules` en `hooks.py` hace que los módulos internos abran dentro de RD Compliance. Al agregar e-CF o Nómina RD, añadir una sección nueva a ese sidebar, no un módulo/ícono aparte. `install.asegurar_navegacion()` recrea el sidebar si falta tras un migrate.
- **Nómina RD:** `nomina_rd/calculos.py` (TSS con topes, ISR anualizado, regalía) lee *Configuracion Nomina RD* (single, editable). `nomina_rd/salario.py` aplica AFP/SFS/ISR y aportes del empleador al Salary Slip de HRMS vía `regional_overrides` (`apply_regional_deductions`, solo si el país del sistema es RD) y `doc_events Salary Slip validate` (siempre); solo en empresas RD. Los componentes se identifican por el campo `rd_concepto_nomina` y se crean en `setup()` con cuentas del catálogo DGII.
- **HRMS es opcional** (`required_apps = ["frappe/erpnext"]`). Todo lo que toque DocTypes de Frappe HR se condiciona con `nomina_rd.hrms_instalado()`: campos de `Salary Component` (`install.DOCTYPES_HRMS`), componentes, cuentas de reclamos de gastos, la sección *Nómina RD* del menú (`install.ajustar_menu_nomina`, la oculta con `hidden`) y los tests de recibos (`skipUnless`). Si HRMS se instala o desinstala después, `after_app_install` / `after_app_uninstall` (`install.al_instalar_app` / `al_desinstalar_app`) activan o retiran la nómina.
- **CI:** `deploy/ci/run-tests.sh` levanta un stack Compose desechable (proyecto `erpnext-rd-ci`, contraseñas aleatorias) y corre los tests; `DEV=1` monta el código, `KEEP=1` lo deja arriba. Nunca toca los volúmenes `deploy_*`. En un sitio nuevo, `before_tests` (`tests/utils.py`) completa el asistente como empresa RD. Lint: ruff 0.12.12 (`ruff check` + `ruff format --check`).
- Padrón RNC (~3 min, ~800 mil registros): en un sitio nuevo se descarga solo en la cola `long` al instalar/migrar si está vacío (`install.programar_padron_inicial`); luego cada día a las 2:00 a. m. de la zona horaria del sitio (`cron` → `padron.encolar`, que lo pasa a la cola `long`; ~22 MB de ZIP, ~270 MB en la tabla). Solo descarga si la DGII publicó un archivo nuevo: guarda su `Last-Modified` en *Configuracion DGII* (`padron_version_dgii`) y lo envía como `If-Modified-Since` (sin cambios responde 304, ~3 s); margen de 1 h porque los servidores de la DGII tienen copias con segundos de diferencia. El botón fuerza la descarga. La lista del padrón tiene desactivado el filtro automático de "últimos 90 días" de Frappe para tablas grandes (`install.lista_padron_sin_filtro_reciente`, solo ese DocType) o con el botón *Actualizar padrón RNC* de Configuración DGII. A mano: `bench --site erp.localhost execute erpnext_rd.padron_rnc.padron.sincronizar_padron`. El servidor de la DGII a veces corta la descarga; hay reintentos.
- **Desinstalación:** Frappe borra lo que tiene módulo de la app (DocTypes, reportes, formatos, Custom Fields, Property Setters con `module`, sidebar). `install.before_uninstall` quita el resto (formato de impresión por defecto, Scheduled Job Types, Dock). Todo Property Setter nuevo debe llevar `module` de la app. Los datos contables del usuario se conservan.
- El sitio local ya tiene la empresa real del usuario (**Dynamics Plastics**): no crear documentos de prueba en él sin permiso. Los tests de integración hacen rollback.
- Al crear DocTypes desde la UI hay que tener `developer_mode` activo en el sitio para que se exporten a JSON en la app. Como la app vive dentro del contenedor, los archivos generados deben copiarse de vuelta al repo (`docker cp`) o, preferiblemente, crearse directamente en el repo.
- En el Containerfile, `sites/apps.txt` no termina en salto de línea: al agregar apps usar `printf '\n<app>\n'` y limpiar líneas vacías.
- El repo fuerza finales de línea LF (`.gitattributes`); los scripts `.sh` deben quedar en LF o fallan en el contenedor.
- **Marketplace de Frappe Cloud (meta):** todo lo nuevo debe poder instalarse sin acceso a la máquina (solo `after_install`/`after_migrate`, patches, DocTypes de configuración y dependencias pip), funcionar sin HRMS y desinstalarse limpio. Requisitos en `docs/PLAN.md`, Fase 7. Para probar sin HRMS: `KEEP=1 DEV=1 deploy/ci/run-tests.sh` y en ese stack `bench new-site sin-hrms.localhost ... --install-app erpnext --install-app erpnext_rd`.
- **Estándar visual: frappe-ui** (la base del escritorio v16). El HTML propio en reportes, diálogos y mensajes usa los tokens CSS del escritorio (`--ink-gray-*` para texto, `--outline-gray-*` para bordes, `--surface-*` para fondos, `--ink-amber-8` para avisos, `--ink-red-6` para errores): nunca colores hex fijos ni clases de Bootstrap, así se adapta solo al modo oscuro. Excepción: los formatos de impresión (van en papel).
- **Panel RD Compliance** (`/rd-compliance`): SPA en `frontend/` con frappe-ui **1.0.2 fijada exacta** (más `yarn.lock`), mismo shell que v16 (`DesktopShell`, `Sidebar`, `PageHeader`). Solo lee: la API `rd_compliance/panel.py` (`contexto`, `resumen`) reutiliza `formatos.obtener` y `declaraciones.resumen_it1/ir17` para que los números cuadren con los reportes; los enlaces abren el escritorio (`/desk/...`). Roles: los de `formatos.ROLES`. El build lo hace `bench build` (script `build` del `package.json` de la raíz → `frontend/`), igual en la imagen y en Frappe Cloud; la salida no se versiona. Usar componentes de frappe-ui antes que HTML propio (cifras: `NumberCard` de `frappe-ui/charts`) y no usar `@framework/ui` (no está en npm). Ojo con frappe-ui 1.x: los radios son numéricos (`rounded-4` = 8px, `rounded-6` = 12px; `rounded-lg/md/sm` ya no existen y no generan nada) y las tarjetas llevan la superficie de los widgets del escritorio: `rounded-6 border border-outline-gray-1 bg-surface-base`. El `body` lleva `bg-surface-base` (sin fondo, en tema oscuro el lienzo queda blanco) y el tema se aplica en `main.js` antes de montar, desde el `desk_theme` del usuario. Revisar siempre en claro y en oscuro. Pantallas nuevas fuera del escritorio (monitor e-CF, portal de empleados) van como rutas de este mismo frontend.
- **Panel dentro del escritorio:** el sidebar enlaza la página de escritorio `panel-cumplimiento` (`rd_compliance/page/panel_cumplimiento/`), que muestra `/rd-compliance` en un iframe. Los enlaces `URL` del sidebar de v16 siempre abren otra pestaña (`target="_blank"` fijo en `sidebar_item.html`), por eso no se usan para pantallas propias. Embebido (`embebido` en `frontend/src/utils.js`), el panel oculta su sidebar, sigue el tema del escritorio aunque cambie, y sus enlaces `/desk/...` navegan el escritorio en la misma ventana (`main.js`). En el móvil se deja el encabezado del escritorio (botón del menú).
- Estilo Python de la app: tabs, comillas dobles, ruff con line-length 110 (ver `pyproject.toml`).

## Control de versiones (obligatorio)

- **Todo cambio se versiona en git.** Al terminar cada unidad de trabajo coherente (feature, fix, cambio de config), hacer commit sin esperar a que el usuario lo pida.
- Mensajes en español con prefijo convencional: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`. Ejemplo: `feat(dgii_fiscal): secuencias NCF con bloqueo por fila`.
- Ramas: `main` = estable/producción, `develop` = integración, `feature/<nombre>` para trabajo nuevo. Fusionar a `main` solo con el visto bueno del usuario.
- Tags `vX.Y.Z` al cerrar cada fase.
- Nunca versionar `deploy/.env`, certificados `.p12`, contraseñas ni tokens.
- Remoto: `origin` = https://github.com/daniellora7/ERPNext-DR-Compilance (público, GPL-3.0). Hacer push de `develop` al terminar cada unidad de trabajo; `main` solo con el visto bueno del usuario. Nunca subir secretos (el repo es público).
