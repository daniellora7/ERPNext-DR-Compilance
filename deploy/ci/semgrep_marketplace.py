"""Aplica a un escaneo de Semgrep los criterios del CI del registro del Marketplace de Frappe
(frappe/marketplace): bloquea un hallazgo Critical o Major (ERROR, CRITICAL o HIGH) o con
`is_blocking: true`; los demás solo se muestran.

Uso (desde la raíz del repo, con las reglas de frappe/marketplace en .marketplace/):
	semgrep scan --config .marketplace/validation/semgrep-rules --metrics=off --json --quiet \
		--exclude .marketplace . > /tmp/semgrep.json
	python3 deploy/ci/semgrep_marketplace.py < /tmp/semgrep.json
"""

import json
import sys

BLOQUEAN = {"ERROR", "CRITICAL", "HIGH"}


def main() -> int:
	escaneo = json.load(sys.stdin)
	for error in escaneo.get("errors", []):
		print(f"error de Semgrep: {error.get('message', error)}")

	bloqueantes = 0
	for hallazgo in escaneo["results"]:
		extra = hallazgo["extra"]
		bloquea = extra.get("metadata", {}).get("is_blocking") is True or extra["severity"] in BLOQUEAN
		bloqueantes += bloquea
		regla = hallazgo["check_id"].rsplit(".", 1)[-1]
		marca = "BLOQUEA" if bloquea else "aviso"
		print(f"{marca:8} {regla}: {hallazgo['path']}:{hallazgo['start']['line']}")
		print(f"         {' '.join(extra['message'].split())}")

	print(f"{bloqueantes} hallazgos bloqueantes.")
	return 1 if bloqueantes else 0


if __name__ == "__main__":
	sys.exit(main())
