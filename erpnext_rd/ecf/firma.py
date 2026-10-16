"""Firma digital del e-CF según el instructivo «Firmado de e-CF» de la DGII.

XMLDSig *enveloped* sobre todo el documento (`Reference URI=""`), canonicalización C14N 1.0 inclusiva,
firma RSA-SHA256, digest SHA-256 y el certificado X509 en `KeyInfo`. La firma va al final del elemento
raíz, sin prefijo (espacio de nombres por defecto de XMLDSig), como en los ejemplos de la DGII.

El certificado es el .p12 del emisor (lo emite una entidad autorizada por el INDOTEL) con su
contraseña. Se implementa con lxml y cryptography (ya incluidas en Frappe), sin dependencias nuevas.
"""

import base64
import copy
import hashlib

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

# XML de terceros (proveedores, la DGII): sin entidades ni red, contra XXE y bombas de entidades
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


def leer(xml: bytes) -> etree._Element:
	return etree.fromstring(xml, PARSER)


def cargar_certificado(p12: bytes, clave: str | None):
	"""(llave privada, certificado) del .p12."""
	llave, certificado, _adicionales = pkcs12.load_key_and_certificates(
		p12, clave.encode() if clave else None
	)
	if llave is None or certificado is None:
		raise ValueError("El archivo .p12 no trae la llave privada y el certificado")
	return llave, certificado


def _c14n(elemento) -> bytes:
	return etree.tostring(elemento, method="c14n", exclusive=False, with_comments=False)


def _c14n_firma(info) -> bytes:
	"""SignedInfo canonicalizado como raíz de su propio documento.

	libxml2 agrega un `xmlns=""` falso al canonicalizar un elemento interno. La copia lleva declarados
	todos los espacios de nombres que SignedInfo tiene en alcance (el de XMLDSig y los del documento, p. ej.
	xmlns:xsi de la semilla), que es la forma C14N inclusiva que calculan los verificadores (xmlsec1)."""
	copia = etree.Element(info.tag, attrib=dict(info.attrib), nsmap=info.nsmap)
	copia.extend(copy.deepcopy(hijo) for hijo in info)
	return _c14n(copia)


def _sub(padre, nombre, **atributos):
	return etree.SubElement(padre, f"{{{DS}}}{nombre}", **atributos)


def firmar(xml: bytes | etree._Element, llave, certificado) -> bytes:
	"""Devuelve el XML con la firma al final del elemento raíz."""
	raiz = leer(xml) if isinstance(xml, bytes) else xml
	for previa in raiz.findall(f"{{{DS}}}Signature"):
		raiz.remove(previa)

	# Transformación enveloped: el digest es del documento sin la firma
	digest = base64.b64encode(hashlib.sha256(_c14n(raiz)).digest()).decode()

	firma = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
	info = _sub(firma, "SignedInfo")
	_sub(info, "CanonicalizationMethod", Algorithm=C14N)
	_sub(info, "SignatureMethod", Algorithm=RSA_SHA256)
	referencia = _sub(info, "Reference", URI="")
	_sub(_sub(referencia, "Transforms"), "Transform", Algorithm=ENVELOPED)
	_sub(referencia, "DigestMethod", Algorithm=SHA256)
	_sub(referencia, "DigestValue").text = digest

	valor = llave.sign(_c14n_firma(info), padding.PKCS1v15(), hashes.SHA256())
	_sub(firma, "SignatureValue").text = base64.b64encode(valor).decode()
	datos = _sub(_sub(firma, "KeyInfo"), "X509Data")
	_sub(datos, "X509Certificate").text = base64.b64encode(
		certificado.public_bytes(serialization.Encoding.DER)
	).decode()
	return etree.tostring(raiz, xml_declaration=True, encoding="utf-8")


def codigo_seguridad(xml_firmado: bytes) -> str:
	"""Los primeros 6 caracteres del valor de la firma (SignatureValue), como pide la DGII."""
	valor = leer(xml_firmado).findtext(f".//{{{DS}}}SignatureValue") or ""
	return valor.strip()[:6]


def verificar(xml_firmado: bytes) -> bool:
	"""Comprueba el digest y la firma con el certificado incluido (para pruebas y diagnósticos)."""
	try:
		raiz = leer(xml_firmado)
		firma = raiz.find(f"{{{DS}}}Signature")
		if firma is None:
			return False
		info = firma.find(f"{{{DS}}}SignedInfo")
		digest = firma.findtext(f".//{{{DS}}}DigestValue")
		valor = base64.b64decode(firma.findtext(f"{{{DS}}}SignatureValue"))
		certificado = x509.load_der_x509_certificate(
			base64.b64decode(firma.findtext(f".//{{{DS}}}X509Certificate"))
		)
	except (etree.XMLSyntaxError, TypeError, ValueError):
		return False

	sin_firma = leer(xml_firmado)
	sin_firma.remove(sin_firma.find(f"{{{DS}}}Signature"))
	if base64.b64encode(hashlib.sha256(_c14n(sin_firma)).digest()).decode() != digest:
		return False
	try:
		certificado.public_key().verify(valor, _c14n_firma(info), padding.PKCS1v15(), hashes.SHA256())
	except Exception:
		return False
	return True


def datos_certificado(certificado) -> dict:
	"""Titular y vigencia, para mostrarlos en el emisor."""
	nombre = certificado.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
	return {
		"titular": nombre[0].value if nombre else certificado.subject.rfc4514_string(),
		"desde": certificado.not_valid_before_utc.date(),
		"hasta": certificado.not_valid_after_utc.date(),
	}
