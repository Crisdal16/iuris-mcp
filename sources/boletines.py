"""Boletines oficiales autonomicos y provinciales (BORM, BOJA, BOCM, BOP...).

Complementa a `regcon.py`, que solo sabe leer convenios publicados en el BOE.
Muchos convenios de sector son autonomicos o provinciales y NO estan en el BOE:
su texto oficial vive en el boletin de su territorio. Este modulo descarga esa
publicacion (PDF o HTML) y extrae el texto, con la misma logica de recorte por
articulo que ya usa regcon.

Honestidad de acceso
--------------------
Se usa el cliente comun (common.http), que se identifica con un User-Agent
veraz. Algunos boletines (el BORM, por ejemplo) estan tras un WAF que sirve un
captcha a los clientes que no se identifican. Identificarse de verdad NO es
evadir el anti-bot: es lo contrario de falsear el agente. Si aun asi el
boletin responde con una pagina de captcha, la tool NO insiste ni disfraza la
peticion: devuelve el enlace oficial para que lo abra el usuario, igual que
hace `cendoj.py`.
"""

from __future__ import annotations

import re

import pymupdf
from selectolax.parser import HTMLParser

from common.http import get
from common.lecturas import recortar

# ---------------------------------------------------------------------------
# Boletines conocidos: construccion de la URL del documento
# ---------------------------------------------------------------------------

BOLETINES: dict[str, dict[str, str]] = {
    "borm": {
        "nombre": "Boletin Oficial de la Region de Murcia",
        "pdf": "https://www.borm.es/services/anuncio/ano/{ano}/numero/{numero}/pdf",
        "portada": "https://www.borm.es/#/home/anuncio/{ano}/{numero}",
        "busqueda": "https://www.borm.es/#/home/busqueda",
    },
}

_RE_CAPTCHA = re.compile(
    r"captcha|perfdrive|shieldsquare|radware|are you a robot", re.IGNORECASE
)
_RE_ART = re.compile(
    r"^(ART[IÍ]CULO|DISPOSICI[OÓ]N|CAP[IÍ]TULO|T[IÍ]TULO|ANEXO)\b", re.IGNORECASE
)


def _norm(t: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").upper()


def _clave_articulo(t: str) -> str:
    t = _norm(t)
    t = re.sub(r"\bART[IÍ]CULOS?\b", " ", t)
    t = re.sub(r"^\s*ARTICULOS?\b", " ", t)
    t = t.split(".", 1)[0]
    return " ".join(t.split())


def _lineas(texto: str) -> list[str]:
    """Limpia el texto: quita cabeceras/pies repetidos de boletin y lineas vacias."""
    basura = re.compile(
        r"^(NPE:\s*\S+|P[áa]gina\s+\d+|N[úu]mero\s+\d+|"
        r"(Lunes|Martes|Mi[ée]rcoles|Jueves|Viernes|S[áa]bado|Domingo),\s+\d+\s+de\s+\w+"
        r"(\s+de\s+\d{4})?)$",
        re.IGNORECASE,
    )
    out = []
    for l in texto.replace("\xa0", " ").splitlines():
        l = " ".join(l.split())
        if l and not basura.match(l):
            out.append(l)
    return out


def _recortar_articulo(lineas: list[str], articulo: str) -> str | None:
    """Extrae el bloque de un articulo. Se queda con la aparicion mas larga
    (evita devolver la entrada del indice en lugar del articulado)."""
    objetivo = _clave_articulo(articulo)
    inicios = [
        i
        for i, l in enumerate(lineas)
        if re.match(r"^Art[ií]culo\s+\S", l) and _clave_articulo(l) == objetivo
    ]
    if not inicios:
        return None
    mejor = None
    for ini in inicios:
        fin = len(lineas)
        for j in range(ini + 1, len(lineas)):
            if _RE_ART.match(lineas[j]):
                fin = j
                break
        bloque = "\n".join(lineas[ini:fin])
        if mejor is None or len(bloque) > len(mejor):
            mejor = bloque
    return mejor


def _texto_de(contenido: bytes, content_type: str) -> tuple[str, str]:
    """Devuelve (texto, formato) de un PDF o HTML."""
    if contenido[:5] == b"%PDF-" or "pdf" in content_type.lower():
        doc = pymupdf.open(stream=contenido, filetype="pdf")
        return "\n".join(p.get_text() for p in doc), f"PDF ({doc.page_count} pags.)"
    html = contenido.decode("utf-8", errors="replace")
    tree = HTMLParser(html)
    for sel in ("div#texto", "div.documento", "main", "article", "body"):
        nodo = tree.css_first(sel)
        if nodo:
            return nodo.text(separator="\n"), "HTML"
    return html, "HTML (sin extraer)"


def leer_boletin(
    url: str = "",
    boletin: str = "",
    ano: str = "",
    numero: str = "",
    articulo: str = "",
    max_chars: int = 14000,
) -> str:
    """Texto oficial de una disposicion publicada en un boletin autonomico o provincial.

    Se le puede dar la URL directa del documento, o bien el boletin + ano + numero
    de anuncio para los boletines conocidos (de momento: BORM).
    """
    boletin = (boletin or "").strip().lower()
    url = (url or "").strip()

    if not url:
        if boletin not in BOLETINES:
            conocidos = ", ".join(sorted(BOLETINES))
            return (
                "Indica la URL oficial del documento, o bien un boletin conocido "
                f"({conocidos}) junto con «ano» y «numero» de anuncio.\n"
                "La URL la obtienes en el buscador del boletin correspondiente."
            )
        if not (ano and numero):
            b = BOLETINES[boletin]
            return (
                f"Para leer del {b['nombre']} necesito «ano» y «numero» de anuncio, "
                f"o la URL directa del PDF.\nBuscador oficial: {b['busqueda']}"
            )
        url = BOLETINES[boletin]["pdf"].format(ano=ano, numero=numero)

    try:
        resp = get(url, accept="application/pdf,text/html;q=0.9")
    except Exception as e:  # noqa: BLE001
        return f"No pude descargar {url}: {e}"

    contenido = resp.content
    ctype = resp.headers.get("content-type", "")

    # WAF / captcha: no se insiste ni se disfraza la peticion (ver docstring).
    if contenido[:5] != b"%PDF-" and _RE_CAPTCHA.search(
        contenido[:4000].decode("utf-8", errors="replace")
    ):
        return (
            "El boletin ha respondido con una pagina de verificacion anti-bot en lugar "
            "del documento. No se insiste ni se disfraza la peticion.\n"
            f"Abre el documento en tu navegador: {url}"
        )

    texto, formato = _texto_de(contenido, ctype)
    lineas = _lineas(texto)
    if not lineas:
        return f"Descargue el documento pero no pude extraer texto.\nEnlace: {url}"

    nombre = BOLETINES.get(boletin, {}).get("nombre", "Boletin oficial")
    cab = f"【{nombre}】" if boletin else "【Boletin oficial】"
    if ano and numero:
        cab += f" anuncio {numero}/{ano}"

    if articulo:
        bloque = _recortar_articulo(lineas, articulo)
        if bloque is None:
            return (
                f"{cab}\nNo encontre el «articulo {articulo}» en el documento "
                f"({formato}, {len(lineas)} lineas). Puede rotularse distinto o estar "
                f"en un anexo.\nEnlace: {url}"
            )
        return f"{cab}\n\nARTICULO {articulo}\n\n{bloque}\n\nFuente: {formato} · {url}"

    cuerpo = "\n".join(lineas)
    cuerpo = recortar(cuerpo, max_chars, titulo=cab,
                      consejo="Para ir directo a un precepto: leer_boletin(..., articulo='N')")
    return f"{cab}\n\n{cuerpo}\n\nFuente: {formato} · {url}"
