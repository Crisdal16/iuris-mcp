"""REGCON — convenios colectivos (Registro y Deposito, Ministerio de Trabajo).

Viabilidad investigada (2026-08):

  * robots.txt de expinterweb.mites.gob.es NO existe (404), asi que no hay
    prohibicion explicita de acceso automatizado.
  * El buscador publico es un POST a
        https://expinterweb.mites.gob.es/regcon/pub/consultaPublicaEstatal
    SIN captcha, pero protegido por un token de sesion
    (`consulta_token_value_id`) que se rellena por JavaScript en el navegador.
    Un POST directo sin ese token devuelve "Se ha producido un error en la
    aplicacion" (probado). => El buscador NO es scriptable de forma honesta:
    exige JS/sesion. Por eso `buscar_convenio` y `vigencia_convenio` funcionan
    en modo HUMANO-EN-EL-BUCLE: devuelven la URL oficial ya orientada y explican
    que filtros marcar. No se evade el anti-bot ni se inventan datos.

  * Lo que SI es automatizable: LEER el texto del convenio una vez publicado en
    el BOE. Los convenios y acuerdos de ambito estatal se publican en el BOE
    (Seccion III) y su texto integro es accesible por HTTP:
        https://www.boe.es/diario_boe/txt.php?id={BOE-A-...}   (HTML)
        https://www.boe.es/boe/dias/AAAA/MM/DD/pdfs/{BOE-A-...}.pdf   (PDF)
    `leer_convenio` baja el HTML (selectolax, contenedor div#textoxslt), y si no
    hay texto cae al PDF con PyMuPDF. De ese texto se extrae ademas el codigo de
    convenio de 14 digitos. Los convenios autonomicos van al boletin de la CCAA
    (BOCM, DOGC, ...) y los provinciales al BOP; para esos, se orienta al usuario.
"""

from __future__ import annotations

import re
import unicodedata

import pymupdf
from selectolax.parser import HTMLParser

from common.http import get

# ---------------------------------------------------------------------------
# URLs oficiales
# ---------------------------------------------------------------------------

REGCON = "https://expinterweb.mites.gob.es/regcon"
REGCON_CONSULTA_PUBLICA = f"{REGCON}/pub/consultaPublicaEstatal"
REGCON_BUSCAR_TEXTOS = f"{REGCON}/pub/buscadorTextosEstatal"
REGCON_ANTERIORES_2010 = f"{REGCON}/pub/consultaPublicaRegconAntiguo"
REGCON_CORRESPONDENCIA = f"{REGCON}/pub/consultaAntiguos"

BOE_TXT = "https://www.boe.es/diario_boe/txt.php?id={id}"
BOE_DOC = "https://www.boe.es/buscar/doc.php?id={id}"
BOE_BUSCADOR = "https://www.boe.es/buscar/boe.php"

# ---------------------------------------------------------------------------
# Mapa de territorios -> codigo de "autoridad laboral" del formulario REGCON.
# Provincias (INE), Comunidades Autonomas y "Estatal". Extraido del propio
# desplegable de la consulta publica.
# ---------------------------------------------------------------------------

TERRITORIOS: dict[str, str] = {
    "ALAVA": "1", "ARABA": "1", "ALBACETE": "2", "ALICANTE": "3", "ALACANT": "3",
    "ALMERIA": "4", "AVILA": "5", "BADAJOZ": "6", "BALEARS": "7", "BALEARES": "7",
    "ILLES BALEARS": "7", "BARCELONA": "8", "BURGOS": "9", "CACERES": "10",
    "CADIZ": "11", "CASTELLON": "12", "CASTELLO": "12", "CIUDAD REAL": "13",
    "CORDOBA": "14", "CORUNA": "15", "A CORUNA": "15", "LA CORUNA": "15",
    "CUENCA": "16", "GIRONA": "17", "GERONA": "17", "GRANADA": "18",
    "GUADALAJARA": "19", "GUIPUZCOA": "20", "GIPUZKOA": "20", "HUELVA": "21",
    "HUESCA": "22", "JAEN": "23", "LEON": "24", "LLEIDA": "25", "LERIDA": "25",
    "RIOJA": "26", "LA RIOJA": "26", "LUGO": "27", "MADRID": "28", "MALAGA": "29",
    "MURCIA": "30", "NAVARRA": "31", "OURENSE": "32", "ORENSE": "32",
    "ASTURIAS": "33", "PALENCIA": "34", "LAS PALMAS": "35", "PALMAS": "35",
    "PONTEVEDRA": "36", "SALAMANCA": "37", "SANTA CRUZ DE TENERIFE": "38",
    "TENERIFE": "38", "CANTABRIA": "39", "SEGOVIA": "40", "SEVILLA": "41",
    "SORIA": "42", "TARRAGONA": "43", "TERUEL": "44", "TOLEDO": "45",
    "VALENCIA": "46", "VALENCIA/VALENCIA": "46", "VALLADOLID": "47",
    "VIZCAYA": "48", "BIZKAIA": "48", "ZAMORA": "49", "ZARAGOZA": "50",
    "CEUTA": "51", "MELILLA": "52",
    # Comunidades Autonomas
    "ANDALUCIA": "53", "ARAGON": "54", "CANARIAS": "55", "CASTILLA Y LEON": "56",
    "CASTILLA-LA MANCHA": "57", "CASTILLA LA MANCHA": "57", "CATALUNA": "58",
    "COMUNITAT VALENCIANA": "59", "COMUNIDAD VALENCIANA": "59",
    "EXTREMADURA": "60", "GALICIA": "61", "PAIS VASCO": "62", "EUSKADI": "62",
    "ESTATAL": "63", "NACIONAL": "63", "ESPANA": "63",
}

# Ambito funcional -> (codigo idAmbFuncionalConsPublica, etiqueta oficial)
AMBITOS: dict[str, tuple[str, str]] = {
    "franja": ("1", "CONVENIOS O ACUERDOS FRANJA"),
    "centro": ("2", "UNO O VARIOS CENTROS DE LA EMPRESA"),
    "empresa": ("3", "EMPRESA O TODOS LOS CENTROS DE UNA EMPRESA"),
    "grupo": ("4", "GRUPO DE EMPRESAS / EMPRESAS VINCULADAS"),
    "sector_local": ("5", "SECTOR INFERIOR A LA PROVINCIA (COMARCAL, LOCAL...)"),
    "sector": ("6", "SECTOR IGUAL O SUPERIOR A LA PROVINCIA"),
    "sector_provincial": ("6", "SECTOR IGUAL O SUPERIOR A LA PROVINCIA"),
}

_RE_BOE_ID = re.compile(r"BOE-A-\d{4}-\d+", re.IGNORECASE)
_RE_CODIGO14 = re.compile(r"\b\d{14}\b")
_RE_PDF = re.compile(r"/boe/dias/\d{4}/\d{2}/\d{2}/pdfs/BOE-A-\d{4}-\d+\.pdf")


def _norm(t: str) -> str:
    """Mayusculas sin tildes ni signos raros, para comparar nombres."""
    d = unicodedata.normalize("NFKD", t)
    s = "".join(c for c in d if not unicodedata.combining(c))
    return " ".join(s.upper().replace("\xa0", " ").split())


def resolver_territorio(territorio: str) -> tuple[str, str] | None:
    """'Madrid' / 'estatal' / 'A Coruna' -> (codigo autoridad laboral, nombre)."""
    if not territorio:
        return None
    n = _norm(territorio)
    if n in TERRITORIOS:
        return TERRITORIOS[n], territorio.strip()
    # Coincidencia laxa: 'provincia de Madrid', 'Comunidad de Madrid'
    for nombre, cod in TERRITORIOS.items():
        if nombre in n or n in nombre:
            return cod, nombre.title()
    return None


def resolver_ambito(ambito: str) -> tuple[str, str]:
    """Normaliza el ambito funcional; por defecto 'sector' (supraprovincial)."""
    a = _norm(ambito).lower().replace(" ", "_") if ambito else "sector"
    return AMBITOS.get(a, AMBITOS["sector"])


def _boe_id(*textos: str) -> str | None:
    """Devuelve el primer identificador BOE-A que aparezca en los argumentos."""
    for t in textos:
        if not t:
            continue
        m = _RE_BOE_ID.search(t)
        if m:
            return m.group(0).upper()
    return None


# ---------------------------------------------------------------------------
# 1) buscar_convenio  (humano-en-el-bucle: el buscador REGCON exige JS/sesion)
# ---------------------------------------------------------------------------

def buscar_convenio(consulta: str, territorio: str = "", ambito: str = "sector",
                    maximo: int = 8) -> str:
    """Localiza un convenio por sector y territorio.

    El buscador publico de REGCON es un POST protegido por un token de sesion
    generado por JavaScript (sin captcha, pero no scriptable de forma honesta),
    de modo que esta funcion prepara la BUSQUEDA OFICIAL para que la ejecute la
    persona: devuelve la URL de la consulta publica de REGCON y los valores de
    filtro ya resueltos (denominacion, territorio, ambito), mas una via BOE.
    """
    consulta = (consulta or "").strip()
    if not consulta and not territorio:
        return "Indica al menos un sector o denominacion (p.ej. «hosteleria»)."

    # Si ya te dan un BOE-A, no hay que buscar: se puede leer directamente.
    bid = _boe_id(consulta)
    if bid:
        return (
            f"«{consulta}» ya es un identificador del BOE ({bid}).\n"
            f"Puedes leer su texto directamente con leer_convenio(codigo=\"{bid}\").\n"
            f"Publicacion oficial: {BOE_DOC.format(id=bid)}"
        )

    cod_amb, etq_amb = resolver_ambito(ambito)
    terr = resolver_territorio(territorio)

    lineas = [
        f"BUSQUEDA DE CONVENIO — «{consulta}»"
        + (f" · territorio: {territorio}" if territorio else "")
        + f" · ambito: {etq_amb}",
        "",
        "El registro oficial es REGCON (Ministerio de Trabajo). Su buscador es",
        "publico y sin captcha, pero valida un token de sesion por JavaScript, por",
        "lo que la consulta debe hacerse en el navegador. Abre esta pagina:",
        "",
        f"  {REGCON_CONSULTA_PUBLICA}",
        "",
        "y rellena los filtros con estos valores ya resueltos:",
        f"  • Denominacion (contiene): {consulta}",
        f"  • Ambito funcional: {etq_amb}",
    ]
    if terr:
        lineas.append(f"  • Ambito territorial / Autoridad laboral: {terr[1]}")
    elif territorio:
        lineas.append(
            f"  • Territorio «{territorio}»: no lo reconoci como provincia/CCAA; "
            f"seleccionalo a mano en el desplegable «Ambito territorial»."
        )
    else:
        lineas.append(
            "  • Ambito territorial: dejalo vacio para ambito estatal o elige la "
            "provincia/CCAA."
        )

    lineas += [
        "",
        "Cada resultado trae el CODIGO DE CONVENIO (14 digitos), el ambito y el",
        "enlace a su publicacion oficial (BOE o boletin autonomico/provincial).",
        "",
        "Alternativa via BOE (solo convenios de ambito estatal): busca en",
        f"  {BOE_BUSCADOR}   -> pestana Seccion III, texto: «convenio colectivo {consulta}».",
        "Cuando tengas el identificador BOE-A, usa leer_convenio para el texto.",
        "",
        "Convenios anteriores al 01/10/2010: " + REGCON_ANTERIORES_2010,
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 2) leer_convenio  (automatizable desde la publicacion en el BOE)
# ---------------------------------------------------------------------------

def _extraer_texto_html(html: str) -> tuple[str, str | None]:
    """Devuelve (texto_plano, url_pdf) del documento BOE en HTML."""
    tree = HTMLParser(html)
    nodo = tree.css_first("div#textoxslt") or tree.css_first("#textoxslt")
    texto = nodo.text(separator="\n") if nodo else ""
    m = _RE_PDF.search(html)
    url_pdf = ("https://www.boe.es" + m.group(0)) if m else None
    return texto, url_pdf


def _lineas(texto: str) -> list[str]:
    return [l.strip() for l in texto.replace("\xa0", " ").splitlines() if l.strip()]


def _clave_articulo(t: str) -> str:
    t = _norm(t)
    t = re.sub(r"\bARTICULOS?\b", " ", t)
    t = t.split(".", 1)[0]
    return " ".join(t.split())


def _recortar_articulo(lineas: list[str], articulo: str) -> str | None:
    """Extrae el bloque de un articulo concreto de la lista de lineas."""
    objetivo = _clave_articulo(articulo)
    cab = re.compile(r"^(ART[IÍ]CULO|DISPOSICI[OÓ]N|CAP[IÍ]TULO|T[IÍ]TULO|ANEXO)\b",
                     re.IGNORECASE)
    ini = None
    for i, l in enumerate(lineas):
        if re.match(r"^Art[ií]culo\s+\S", l) and _clave_articulo(l) == objetivo:
            ini = i
            break
    if ini is None:
        return None
    fin = len(lineas)
    for j in range(ini + 1, len(lineas)):
        if cab.match(lineas[j]):
            fin = j
            break
    return "\n".join(lineas[ini:fin])


def leer_convenio(codigo: str = "", consulta: str = "", territorio: str = "",
                  articulo: str = "") -> str:
    """Texto del convenio (o de un articulo) desde su publicacion en el BOE.

    Necesita un identificador BOE-A (en `codigo` o en `consulta`). Con el codigo
    REGCON de 14 digitos o solo texto libre no se puede resolver la publicacion
    sin el buscador REGCON (JS), asi que en ese caso se redirige a buscar_convenio.
    """
    bid = _boe_id(codigo, consulta)
    if not bid:
        pista = (codigo or consulta or "").strip()
        if _RE_CODIGO14.search(pista):
            return (
                f"«{pista}» parece un codigo REGCON de 14 digitos. Para leer su texto "
                f"necesito el identificador BOE-A de su publicacion, que se obtiene en "
                f"el buscador oficial (no automatizable sin navegador):\n"
                f"  {REGCON_CONSULTA_PUBLICA}\n"
                f"Localiza el convenio, abre su publicacion en el BOE y pasame el BOE-A."
            )
        return (
            "leer_convenio necesita un identificador del BOE (BOE-A-AAAA-N).\n"
            "Si no lo tienes, localiza primero el convenio con buscar_convenio"
            + (f"(«{consulta or territorio}»)" if (consulta or territorio) else "")
            + " y abre su publicacion oficial."
        )

    # 1) Intento HTML (rapido, con articulos direccionables).
    try:
        html = get(BOE_TXT.format(id=bid), accept="text/html").text
    except Exception as e:  # noqa: BLE001
        return (
            f"No pude descargar el documento {bid} del BOE: {e}\n"
            f"Enlace oficial: {BOE_DOC.format(id=bid)}"
        )

    texto, url_pdf = _extraer_texto_html(html)

    # 2) Respaldo PDF con PyMuPDF si el HTML no trae cuerpo.
    fuente = "BOE (HTML)"
    if len(texto.strip()) < 200 and url_pdf:
        try:
            pdf = get(url_pdf, accept="application/pdf").content
            doc = pymupdf.open(stream=pdf, filetype="pdf")
            texto = "\n".join(p.get_text() for p in doc)
            fuente = "BOE (PDF, PyMuPDF)"
        except Exception as e:  # noqa: BLE001
            return (
                f"El documento {bid} no traia texto en HTML y fallo el PDF: {e}\n"
                f"Enlace oficial: {BOE_DOC.format(id=bid)}"
            )

    if not texto.strip():
        return (
            f"No pude extraer texto de {bid}. Consulta la publicacion oficial:\n"
            f"{BOE_DOC.format(id=bid)}"
        )

    lineas = _lineas(texto)
    titulo = lineas[0] if lineas else bid
    mcod = _RE_CODIGO14.search(texto)
    codigo_conv = mcod.group(0) if mcod else None

    cab = f"【Convenio {bid}】"
    if codigo_conv:
        cab += f" · codigo REGCON {codigo_conv}"

    if articulo:
        bloque = _recortar_articulo(lineas, articulo)
        if bloque is None:
            return (
                f"{cab}\nNo encontre el «articulo {articulo}» en {bid}. "
                f"Puede que el convenio rotule distinto o este en anexos.\n"
                f"Texto completo: {BOE_DOC.format(id=bid)}"
            )
        return (
            f"{cab}\n\n{bloque}\n\n"
            f"Fuente: {fuente} · {BOE_DOC.format(id=bid)}"
        )

    cuerpo = "\n".join(lineas)
    if len(cuerpo) > 12000:
        cuerpo = cuerpo[:12000] + "\n[...] (texto truncado; pide un articulo concreto)"
    return (
        f"{cab}\n{titulo}\n\n{cuerpo}\n\n"
        f"Fuente: {fuente} · {BOE_DOC.format(id=bid)}"
    )


# ---------------------------------------------------------------------------
# 3) vigencia_convenio  (la autoridad es REGCON; estado no automatizable)
# ---------------------------------------------------------------------------

def vigencia_convenio(codigo: str) -> str:
    """Estado de vigencia y tramites de un convenio.

    El estado de vigencia (no denunciado, denunciado, derogado, anulado...) y los
    tramites viven en REGCON, cuyo buscador exige JavaScript. No es automatizable
    de forma honesta, asi que se orienta a la consulta oficial. Si se pasa un
    identificador BOE-A, ademas se enlaza su publicacion.
    """
    codigo = (codigo or "").strip()
    bid = _boe_id(codigo)

    lineas = ["ESTADO DE VIGENCIA Y TRAMITES", ""]
    if bid:
        lineas += [
            f"Identificador BOE {bid}. Su publicacion original esta en:",
            f"  {BOE_DOC.format(id=bid)}",
            "Ese enlace muestra el texto y, al pie, las disposiciones que lo",
            "modifican (revisiones salariales, prorrogas, denuncias) publicadas en BOE.",
            "",
        ]
    elif _RE_CODIGO14.search(codigo):
        lineas += [f"Codigo REGCON {codigo}.", ""]
    elif codigo:
        lineas += [f"Referencia «{codigo}».", ""]

    lineas += [
        "El estado de vigencia oficial (NO DENUNCIADO / DENUNCIADO / TEXTO DEROGADO /",
        "ANULADO POR RESOLUCION JUDICIAL / PLAN DE IGUALDAD VIGENTE...) y el historico",
        "de tramites solo son consultables en el registro REGCON, cuyo buscador",
        "requiere navegador (token de sesion por JavaScript). No es automatizable.",
        "",
        "Consulta el estado en la consulta publica de REGCON:",
        f"  {REGCON_CONSULTA_PUBLICA}",
        "  (filtra por «Codigo de convenio» o denominacion y mira «Estado de vigencia»).",
    ]
    return "\n".join(lineas)
