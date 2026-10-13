# Plan: ERPNext v16.50 + HRMS + localización República Dominicana, desplegado en Dokploy

## Contexto
El usuario quiere un ERPNext propio, versionado en GitHub y desplegado en Dokploy, con:
- ERPNext v16.50.0 (frappe v16.51.1, HRMS v16.50.0) + Frappe HR (HRMS) para RH y nómina.
- Una app propia de localización RD: NCF / e-CF emitidos **directamente** ante la DGII, reportes 606/607/608/IT-1, validación RNC/Cédula, nómina RD (TSS/AFP/SFS/ISR/INFOTEP/regalía).
- Base para seguir agregando funcionalidades después.

Proyecto en `D:\Code Projects 2\ERPNext`. Git 2.56 y Docker 29.8 instalados.

**Una sola instancia, una sola base de datos:** un único sitio Frappe (p. ej. `erp.tudominio.com`) = una única base MariaDB 11.x. ERPNext, HRMS y `erpnext_rd` se instalan los tres en ese mismo sitio (`bench --site <sitio> install-app ...`), así que comparten tablas, usuarios, permisos, compañías, empleados, clientes y contabilidad. Si hay varias empresas, se manejan como varias *Company* dentro del mismo sitio. MariaDB se usa porque es la base de datos oficial y probada de ERPNext/HRMS.

**Principio clave:** no hacer fork de ERPNext/Frappe. Toda la personalización vive en una app propia (`erpnext_rd`) instalada sobre ERPNext/HRMS oficiales. Así puedes actualizar a 16.51, 16.52… sin conflictos de merge.

## Estado actual (actualizado 2026-10-12)

| Fase | Estado |
|---|---|
| 0 — Entorno y descarga | ✅ Hecho. Versiones verificadas: frappe v16.51.1, erpnext v16.50.0, hrms v16.50.0. Se usa Docker local (imagen propia) en lugar de devcontainer. |
| 1 — Despliegue | 🟡 Local listo: `deploy/Containerfile` + `deploy/compose.yaml`, sitio `erp.localhost` en http://localhost:8090 con las 4 apps en una sola base MariaDB. **Pendiente:** repo en GitHub, CI (`build-image.yml`, `ci.yml`), Dokploy, backups. |
| 2 — Base fiscal DGII | 🟡 Implementado en `feature/dgii-fiscal`: tipos de comprobante (21), Secuencia NCF con bloqueo, NCF en ventas/compras, RNC/Cédula, padrón (793 985 registros), 16 tests. **Pendiente:** prueba de punta a punta con facturas reales, NCF en POS Invoice, formato de impresión. |
| 3 — Reportes DGII | ⏳ Siguiente |
| 4 — e-CF | ⏳ |
| 5 — Nómina RD | ⏳ |

Decisión: el usuario quiere probar todo en Docker local antes de configurar GitHub y Dokploy.

## Estructura del repo (GitHub, privado: `erpnext-rd`)
```
erpnext-rd/
├── apps/erpnext_rd/            # app Frappe propia (bench new-app)
│   └── erpnext_rd/
│       ├── dgii_fiscal/        # módulo: NCF, tipos de comprobante, campos fiscales
│       ├── ecf/                # módulo: e-CF (XML, firma, envío, consulta, recepción)
│       ├── dgii_reportes/      # módulo: 606, 607, 608, 609, IT-1 helper, IR-17
│       ├── padron_rnc/         # módulo: padrón RNC/Cédula
│       ├── nomina_rd/          # módulo: TSS, ISR, INFOTEP, regalía, IR-3, archivo SUIR
│       ├── fixtures/           # custom fields, property setters, print formats
│       └── hooks.py
├── deploy/
│   ├── apps.json               # frappe/erpnext/hrms (tags v16.50.0) + erpnext_rd
│   ├── compose.yaml            # stack para Dokploy
│   └── .env.example
├── .devcontainer/              # entorno de desarrollo (basado en frappe_docker)
├── .github/workflows/
│   ├── ci.yml                  # lint + tests de la app en cada PR
│   └── build-image.yml         # build imagen → GHCR en tags/main
└── README.md
```
Ramas: `main` (producción), `develop` (staging), ramas `feature/*` con PR. Versionado semántico con tags `v1.0.0` → cada tag publica imagen `ghcr.io/<usuario>/erpnext-rd:<tag>`.

## Fase 0 — Entorno local y descarga
1. Verificar que el tag `v16.5.x` existe en `frappe/frappe`, `frappe/erpnext` y `frappe/hrms` (HRMS puede tener su propio número; usar el tag de la rama `version-16` compatible). Fijar versiones exactas en `deploy/apps.json`.
2. `git init` del repo, crear repo privado en GitHub.
3. Clonar `frappe/frappe_docker` como referencia (no dentro del repo) y copiar su `.devcontainer` para desarrollar en Docker/WSL2 en Windows.
4. Dentro del devcontainer: `bench init --frappe-branch <tag v16.5>`, `bench get-app erpnext`, `bench get-app hrms`, `bench new-app erpnext_rd`, `bench new-site dev.localhost`, instalar las 3 apps.

## Fase 1 — Despliegue mínimo en Dokploy (antes de programar la localización)
1. `build-image.yml`: usa el Containerfile *layered* de frappe_docker (`images/layered/Containerfile`) con `APPS_JSON_BASE64` generado de `deploy/apps.json`; la app propia se referencia por URL del repo con token (`secrets.GH_PAT`). Publica en GHCR.
2. `deploy/compose.yaml` basado en `pwd.yml` de frappe_docker: servicios `backend`, `frontend` (nginx), `websocket`, `queue-short`, `queue-long`, `scheduler`, `configurator`, `create-site`, `db` (MariaDB 11.x), `redis-cache`, `redis-queue`; volúmenes `sites`, `db-data`, `logs`.
3. En Dokploy: proyecto → servicio **Docker Compose** desde el repo GitHub, ruta `deploy/compose.yaml`, variables (`ERPNEXT_IMAGE_TAG`, `DB_ROOT_PASSWORD`, `SITE_NAME`, `ADMIN_PASSWORD`), dominio en el servicio `frontend` puerto 8080 con HTTPS (Traefik de Dokploy).
4. Backups: `bench backup --with-files` vía cron de Dokploy/scheduler + volumen MariaDB; documentar restauración.
5. Flujo de actualización: nuevo tag → imagen → cambiar `ERPNEXT_IMAGE_TAG` → redeploy → `bench --site all migrate` (servicio one-shot `migrate` en compose).

## Fase 2 — Base fiscal DGII (módulo `dgii_fiscal` + `padron_rnc`)
- Custom fields (vía fixtures) en Company, Customer, Supplier: tipo de identificación (RNC/Cédula/Pasaporte), RNC.
- DocType **Tipo Comprobante Fiscal** (B01, B02, B04, B11, B13, B14, B15, B16, B17 y E31, E32, E33, E34, E41, E43, E44, E45, E46, E47).
- DocType **Secuencia NCF** (prefijo, rango autorizado, desde/hasta, vencimiento, próximo número) con bloqueo `SELECT … FOR UPDATE` para no duplicar.
- Hooks `doc_events` en Sales/Purchase Invoice: asignar NCF en `on_submit`, validar RNC, NCF modificado en notas de crédito, tipo de ingreso, tipo de gasto (606), ITBIS facturado/retenido, ISR retenido, forma de pago.
- Padrón RNC: DocType **Contribuyente DGII**, job programado que descarga el ZIP del padrón público de la DGII e importa; autocompletar nombre/razón social al escribir RNC; validación de dígito verificador de RNC y Cédula.

## Fase 3 — Reportes DGII (módulo `dgii_reportes`)
Script reports + exportación TXT en el formato oficial:
- **606** (compras), **607** (ventas), **608** (anulados), **609** (pagos al exterior).
- Resumen de apoyo para **IT-1** e **IR-17** (retenciones).
- Validaciones previas (RNC inválido, NCF duplicado, montos negativos) antes de exportar.

## Fase 4 — e-CF directo con DGII (módulo `ecf`)
- DocType **Configuración e-CF**: ambiente (TesteCF / CerteCF / eCF), URLs, certificado `.p12` (archivo privado) + contraseña (campo Password cifrado).
- Generación de XML según XSD oficiales de la DGII por tipo (E31…E47), validación contra XSD con `lxml`.
- Firma XMLDSig (RSA-SHA256) con `signxml`/`cryptography`.
- Autenticación: obtener semilla → firmarla → validar → token Bearer (cacheado en Redis hasta su vencimiento).
- Envío a Recepción, guardar TrackId; job programado de **consulta de estado** (Aceptado / Aceptado condicional / Rechazado) en DocType **Log e-CF**.
- **RFCE** (resumen de facturas de consumo E32 < umbral) y su envío.
- Print format con **código de seguridad** y **QR** con la URL de timbre.
- Endpoints públicos (`@frappe.whitelist(allow_guest=True)` con validación de firma) para **recepción de e-CF** de proveedores y **aprobación comercial**.
- Contingencia: cola de reintentos si la DGII no responde.
- Proceso de certificación DGII: el set de pruebas que exige la DGII se correrá en CerteCF antes de pasar a producción (esto lo gestiona el usuario con la DGII; el código deja herramientas para generarlo).

## Fase 5 — Nómina RD (módulo `nomina_rd`, sobre HRMS)
- DocType singleton **Configuración Nómina RD** con tasas y topes editables (AFP empleado/empleador, SFS empleado/empleador, SRL, INFOTEP, topes en salarios mínimos, escala anual ISR) — no se hardcodean porque cambian.
- Salary Components y Salary Structure plantilla; fórmulas que llaman funciones Python de la app para ISR (proyección anual) y topes TSS.
- Regalía pascual (salario 13), vacaciones, cesantía/preaviso (calculadora de prestaciones).
- Exportes: archivo de **autodeterminación TSS/SUIR**, **IR-3** mensual, **IR-13** anual.

## Fase 6 — Funcionalidades futuras
Cada nueva funcionalidad = nuevo módulo en `erpnext_rd` (o nueva app si es independiente), en rama `feature/*`, con PR, CI verde y tag de versión.

## Código existente a aprovechar (investigado 2026-10-12)
No existe una app de ERPNext que cubra todo (e-CF + reportes + nómina RD). Tomaremos piezas como base o referencia:

| Repo | Uso en nuestro plan | Licencia / estado |
|---|---|---|
| [LewisMojica/dgii-compliance](https://github.com/LewisMojica/dgii-compliance) (Frappe) | **Base o referencia principal de la Fase 2**: secuencias NCF, asignación a facturas, reportes DGII. Revisar su modelo de DocTypes y su compatibilidad con v16 antes de copiar o adaptar | GPL-3.0, 84 commits, 3 estrellas, sin releases → poco maduro, auditar |
| [odoo-dominicana/l10n-dominicana](https://github.com/odoo-dominicana/l10n-dominicana) (Odoo, `l10n_do_accounting`) | Referencia de reglas de negocio: tipos de comprobante, validaciones, norma 06-18, NCF modificado | LGPL-3, la localización RD más madura (110 estrellas) |
| [angelpimentell/python-dgii-signer](https://github.com/angelpimentell/python-dgii-signer) (Python) | Referencia para la firma XML con .p12 (Fase 4) | **Sin licencia visible** → no copiar código, solo estudiarlo |
| [dev-fcastro/dgii-ecf](https://github.com/dev-fcastro/dgii-ecf) (.NET) | Referencia completa del flujo e-CF: semilla/token, firma (XML-DSig enveloped, C14N inclusivo, RSA-SHA256), recepción, aprobación comercial, anulaciones, consultas | Solo como referencia de protocolo |
| [victors1681/dgii-ecf](https://github.com/victors1681/dgii-ecf), [ithesk/firmadgii](https://github.com/ithesk/firmadgii) (Node) | Referencia de autenticación y RFCE (< RD$250,000) | Referencia |
| [Ruben890/RNC_DGII_DB](https://github.com/Ruben890/RNC_DGII_DB) (Python) | Lógica de descarga e importación del padrón RNC (Fase 2) | Revisar licencia |
| [CarlsRemy/DGII-UTILS](https://github.com/CarlsRemy/DGII-UTILS), [franklinmdev/dgii-ts](https://github.com/franklinmdev/dgii-ts) | Algoritmos de validación de RNC, cédula, NCF y e-NCF, para portarlos a Python | Revisar licencia |
| [alexander0205/vera PR #69](https://github.com/alexander0205/vera/pull/69) | Referencia de cálculo de nómina RD (AFP, SFS, ISR, INFOTEP, SRL, topes) con tasas 2026 | Otro stack; verificar tasas con TSS/DGII |
| Instructivo oficial DGII "Firmado de e-CF" + XSD oficiales | **Fuente de verdad** para la firma y el XML | Oficial |

Evaluación (2026-10-12): `dgii-compliance` es v15, sin bloqueo de secuencia (NCF duplicables), solo B01/B02/B14/B15 y con errores de sintaxis → **no se adopta**; se escribió `dgii_fiscal` propio tomando ideas (URL del padrón, excluir facturas POS consolidadas).

Reglas: solo se copia código con licencia compatible (GPL-3/LGPL-3/MIT); lo que no tenga licencia se usa únicamente como referencia. Primer paso de la Fase 2: clonar `dgii-compliance` en el devcontainer, instalarlo en v16 y decidir entre **adoptarlo como base del módulo `dgii_fiscal`** o reescribirlo tomando sus ideas.

## Archivos críticos a crear
- `apps/erpnext_rd/erpnext_rd/hooks.py` — doc_events, scheduler_events, fixtures.
- `deploy/apps.json`, `deploy/compose.yaml`, `.github/workflows/build-image.yml`.
- `apps/erpnext_rd/erpnext_rd/ecf/firma.py`, `ecf/dgii_client.py`, `ecf/xml_builder.py`.
- `apps/erpnext_rd/erpnext_rd/dgii_fiscal/ncf.py`.
- `apps/erpnext_rd/erpnext_rd/nomina_rd/calculos.py`.

Reutilizar: frappe_docker (`images/layered/Containerfile`, `pwd.yml`, `.devcontainer`), Salary Structure/Payroll Entry de HRMS, Script Report y Print Format de Frappe, `frappe.enqueue`/scheduler para jobs.

## Verificación
- Local: `bench --site dev.localhost run-tests --app erpnext_rd` (tests de NCF, dígito verificador RNC, cálculo ISR/TSS con casos conocidos, XML válido contra XSD, firma verificable).
- CI en GitHub Actions corre esos tests en cada PR.
- Fase 1: abrir el dominio de Dokploy, login, crear compañía RD, confirmar que ERPNext + HRMS + erpnext_rd aparecen en *Installed Apps* del mismo sitio (`bench --site <sitio> list-apps`) y que existe una sola base de datos en MariaDB.
- Fase 3: comparar TXT 606/607 generados con el validador/herramienta de la DGII.
- Fase 4: enviar e-CF de prueba en **TesteCF** y verificar estado "Aceptado"; luego completar set de CerteCF.
- Fase 5: nómina de prueba con empleados cuyos montos se cotejan contra la calculadora de la TSS/DGII.

## Orden de ejecución propuesto
Empezar por Fase 0 + Fase 1 (ERPNext 16.50 + HRMS corriendo primero en Docker local, luego en Dokploy con el repo y CI/CD listos), luego 2 → 3 → 4 → 5 de forma incremental, con un tag por fase.

## Requisitos del usuario (no automatizables por Claude)
- Servidor con Dokploy (mín. 4 GB RAM, 2 vCPU recomendados), dominio apuntando a él.
- Cuenta GitHub + PAT para GHCR/repos privados (lo configuras tú en Secrets).
- Certificado digital de firma (.p12) emitido por entidad autorizada y alta como emisor electrónico ante la DGII.
