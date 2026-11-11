"""Compatibilidad de Frappe Suite (rama develop) con Frappe v16.

Suite (Drive, commit b6ec679d5) llama `File.get_site_url_prefix()`, que solo existe en Frappe develop (v17).
En v16 falla todo adjunto de un archivo privado que ya existe (p. ej. el XML o la foto de la captura de
compras). Se agrega el método con `extend_doctype_class`, sin tocar Suite ni Frappe; si la clase base ya
lo trae, se usa el de la base.
"""

from frappe.utils import get_url


class FileCompatSuite:
	def get_site_url_prefix(self) -> str:
		"""La URL del sitio si `file_url` empieza con ella (Frappe la quita después); si no, vacío.

		Mismo código que Frappe develop (`frappe/core/doctype/file/file.py`, MIT).
		"""
		base = getattr(super(), "get_site_url_prefix", None)
		if base:
			return base()
		site_url = get_url()
		return site_url if (self.file_url or "").startswith(site_url + "/") else ""
