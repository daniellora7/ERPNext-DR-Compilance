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
- **No hacer fork ni modificar** el código de Frappe, ERPNext o HRMS. Toda personalización va en `apps/erpnext_rd` mediante DocTypes propios, `hooks.py` (`doc_events`, `scheduler_events`, `override_*`), Custom Fields y Property Setters exportados como fixtures, y patches.
- Tasas y topes que cambian por ley (TSS, ISR, INFOTEP, etc.) van en DocTypes de configuración editables, nunca hardcodeados.
- Solo copiar código de terceros con licencia compatible (GPL-3, LGPL-3 o MIT). Repos sin licencia solo sirven de referencia. La app es GPL-3.0.

## Estructura

```
apps/erpnext_rd/               App Frappe propia
  erpnext_rd/
    hooks.py                   Hooks de la app (required_apps = erpnext, hrms)
    modules.txt                Módulos: ERPNext RD, DGII Fiscal, ECF, DGII Reportes, Padron RNC, Nomina RD
    dgii_fiscal/               NCF, tipos de comprobante, campos fiscales
    ecf/                       e-CF: XML, firma, envío/consulta DGII, recepción
    dgii_reportes/             606, 607, 608, 609, apoyo IT-1 / IR-17
    padron_rnc/                Padrón RNC/Cédula y validaciones
    nomina_rd/                 TSS, ISR, INFOTEP, regalía, IR-3, archivo SUIR
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

# Aplicar cambios de erpnext_rd: rebuild + up (create-site corre migrate si el sitio existe)
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build

# Bench dentro del contenedor
docker exec deploy-backend-1 bench --site erp.localhost list-apps
docker exec deploy-backend-1 bench --site erp.localhost migrate
docker exec deploy-backend-1 bench --site erp.localhost console
docker exec deploy-backend-1 bench --site erp.localhost mariadb

# Tests de la app
docker exec deploy-backend-1 bench --site erp.localhost set-config allow_tests true
docker exec deploy-backend-1 bench --site erp.localhost run-tests --app erpnext_rd

# Logs
docker logs -f deploy-backend-1
docker logs deploy-create-site-1
```

- URL local: http://localhost:8090 (el 8080 lo usa otro proyecto del usuario, `plastidel-dev-api`; no tocarlo).
- Sitio: `erp.localhost`. Usuario `Administrator`; la contraseña es `ADMIN_PASSWORD` en `deploy/.env`. No repetir contraseñas en el chat.
- Los volúmenes Docker (`deploy_sites`, `deploy_db-data`) guardan los datos; `down -v` los borra. No usarlo sin confirmación del usuario.

## Notas técnicas

- El código de `erpnext_rd` se copia dentro de la imagen; cualquier cambio requiere rebuild. Si el desarrollo se vuelve lento, montar `apps/erpnext_rd` como volumen en un override de desarrollo.
- Al crear DocTypes desde la UI hay que tener `developer_mode` activo en el sitio para que se exporten a JSON en la app. Como la app vive dentro del contenedor, los archivos generados deben copiarse de vuelta al repo (`docker cp`) o, preferiblemente, crearse directamente en el repo.
- En el Containerfile, `sites/apps.txt` no termina en salto de línea: al agregar apps usar `printf '\n<app>\n'` y limpiar líneas vacías.
- El repo fuerza finales de línea LF (`.gitattributes`); los scripts `.sh` deben quedar en LF o fallan en el contenedor.
- Estilo Python de la app: tabs, comillas dobles, ruff con line-length 110 (ver `apps/erpnext_rd/pyproject.toml`).

## Control de versiones (obligatorio)

- **Todo cambio se versiona en git.** Al terminar cada unidad de trabajo coherente (feature, fix, cambio de config), hacer commit sin esperar a que el usuario lo pida.
- Mensajes en español con prefijo convencional: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`. Ejemplo: `feat(dgii_fiscal): secuencias NCF con bloqueo por fila`.
- Ramas: `main` = estable/producción, `develop` = integración, `feature/<nombre>` para trabajo nuevo. Fusionar a `main` solo con el visto bueno del usuario.
- Tags `vX.Y.Z` al cerrar cada fase.
- Nunca versionar `deploy/.env`, certificados `.p12`, contraseñas ni tokens.
- Aún no hay remoto en GitHub: no crear remotos ni hacer push hasta que el usuario lo pida.
