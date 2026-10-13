# ERPNext RD

ERPNext v16.50.0 + Frappe HR v16.50.0 + **erpnext_rd** (localización República Dominicana), empaquetado en Docker para correr en local y desplegar en Dokploy.

Una sola instancia: un sitio Frappe = una base de datos MariaDB, con las tres apps instaladas.

## Estructura

| Ruta | Contenido |
|---|---|
| `apps/erpnext_rd/` | App Frappe propia (módulos DGII Fiscal, ECF, DGII Reportes, Padron RNC, Nomina RD) |
| `deploy/apps.json` | Versiones fijadas de ERPNext y HRMS |
| `deploy/Containerfile` | Imagen con Frappe + ERPNext + HRMS + erpnext_rd |
| `deploy/compose.yaml` | Stack completo (MariaDB, Redis, backend, frontend, workers, scheduler) |
| `deploy/.env.example` | Variables; copiar a `deploy/.env` |

## Correr en local

Requiere Docker Desktop abierto.

```bash
cp deploy/.env.example deploy/.env   # cambiar contraseñas
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f create-site
```

Abrir http://localhost:8090 — usuario `Administrator`, contraseña `ADMIN_PASSWORD` del `.env`.

Comprobar apps instaladas:

```bash
docker compose -f deploy/compose.yaml --env-file deploy/.env exec backend bench --site erp.localhost list-apps
```

## Actualizar

- **erpnext_rd**: cambiar código → `up -d --build` (el servicio `create-site` corre `migrate`).
- **ERPNext/HRMS/Frappe**: cambiar tags en `deploy/apps.json` y `FRAPPE_BRANCH` en `deploy/Containerfile` → `up -d --build`.

## Ramas

`main` = producción, `develop` = staging, `feature/*` vía PR. Tags `vX.Y.Z` por versión.
