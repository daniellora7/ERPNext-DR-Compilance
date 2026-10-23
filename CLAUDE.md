# CLAUDE.md

Responder en español. **ERPNext RD**: ERPNext + Frappe HR + app `erpnext_rd` (localización RD: NCF, e-CF, DGII, padrón RNC, nómina). Docs: `docs/PLAN.md` (pendientes), `docs/NOTAS-TECNICAS.md` (módulos), `docs/lineamientos-diseno-frappe.md` (interfaz), `docs/marketplace.md`; actualizarlos al cambiar algo.

Versiones: Frappe v16.52.0 (`deploy/Containerfile`), ERPNext v16.51.1, HRMS v16.51.0 y Builder v1.36.0 (`deploy/apps.json`), MariaDB 11.8, Python 3.14.

## Reglas

- Un sitio, una base MariaDB; varias empresas = varias *Company*.
- No modificar Frappe/ERPNext/HRMS: todo en `erpnext_rd` (hooks, overrides, campos y Property Setters por código con `module` de la app, patches).
- Tasas y topes legales en DocTypes de configuración, nunca en el código.
- Lógica fiscal/nómina solo si `ncf.es_empresa_rd`; lo que dependa del régimen, según el perfil tributario. Normas nuevas: confirmar en el texto oficial.
- HRMS opcional: condicionar con `nomina_rd.hrms_instalado()`.
- Pasar Semgrep del Marketplace: consultas con `frappe.qb` o `frappe.get_all` (no `frappe.db.sql`), `str(e)` en `_().format()`, commits manuales con `# nosemgrep: <regla>`, tipos en métodos whitelisted y `methods=["POST"]` en los que escriben.
- Interfaz frappe-ui: solo tokens CSS (`--ink-*`, `--surface-*`, `--outline-*`), nunca hex ni Bootstrap; revisar claro y oscuro.
- Formatos imprimibles editables en el constructor de Frappe (ver `erpnext_rd/formatos.py`).
- Terceros solo GPL-3, LGPL-3 o MIT.

## Entorno local

- http://localhost:8090, sitio `erp.localhost`. **No tocar el 8080** (otro proyecto).
- Contraseñas en `deploy/.env`: no repetirlas en el chat.
- Empresa real (Dynamics Plastics): sin documentos de prueba sin permiso; `bench backup --with-files` antes de actualizar.
- **`down -v` nunca sin confirmación.**

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.dev.yaml --env-file deploy/.env up -d
docker restart deploy-backend-1 deploy-queue-short-1 deploy-queue-long-1 deploy-scheduler-1
docker exec deploy-backend-1 bench --site erp.localhost migrate
docker exec deploy-backend-1 bench --site erp.localhost run-tests --app erpnext_rd
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/w" -w /w ghcr.io/astral-sh/ruff:0.12.12 check erpnext_rd
```

## Estilo y git

- Python con tabs, comillas dobles, ruff (110). Repo en LF. Editar con Edit/Write o `python -X utf8`, no heredocs.
- Reportes sin tilde en el nombre; título con tilde en `locale/es.po`.
- Commit local de cada unidad de trabajo, en español con prefijo (`feat:`, `fix:`...). **Push, PR y merge solo si el usuario lo pide.** Ramas `main`, `develop`, `feature/*`.
- Repo público: nunca versionar `.env`, `.p12`, contraseñas ni tokens.
