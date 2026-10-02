"""MERCANTIL — BORME (Boletin Oficial del Registro Mercantil) via la API OFICIAL
de datos abiertos del BOE. Mismo servicio que sources/boe.py, otro sumario.

Endpoint (verificado 2026-08-25 contra el BORME de 2026-08-14):
  https://www.boe.es/datosabiertos/api/borme/sumario/{AAAAMMDD}   -> JSON

Estructura del sumario BORME (difiere algo del BOE):
  data.sumario.metadatos          -> {publicacion: 'BORME', fecha_publicacion}
  data.sumario.diario[]           -> uno o varios numeros del dia, cada uno:
      .numero                     -> nº de BORME
      .sumario_diario             -> {identificador BORME-S-..., url_pdf}  (sin titulo)
      .seccion[]                  -> codigo (A/B/C), nombre, y segun la seccion:
          .item[]                 -> secciones A y B (lista de items)
          .apartado[].item[]      -> seccion C (items agrupados por epigrafe)
  item = {identificador BORME-A|B|C-..., titulo,
          url_pdf{texto,...}, url_html, url_xml}

Secciones del BORME:
  A  Empresarios. Actos inscritos (constituciones, ceses, nombramientos,
     ampliaciones de capital...). Los items A se agrupan por PROVINCIA:
     el 'titulo' es el nombre de la provincia, no el de una empresa.
  B  Empresarios. Otros actos publicados en el Registro Mercantil.
  C  Anuncios y avisos legales (convocatorias de juntas, reducciones de
     capital, fusiones, disolucion/liquidacion...). Aqui el 'titulo' SI es
     la denominacion social de la sociedad anunciante.

AVISO JURIDICO: el BORME es un INDICE de publicidad legal, SIN fe publica
registral y SIN cuentas anuales. Los datos con valor certificante (nota simple,
certificacion, cuentas depositadas, titularidad real) se obtienen en el Registro
Mercantil correspondiente / Registro Mercantil Central, de pago y sin API abierta.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote_plus

from common.http import get_json

API = "https://www.boe.es/datosabiertos/api"

# Buscadores oficiales para el modo humano-en-el-bucle (no hay API abierta que
# permita buscar una sociedad por nombre de forma barata y estable).
URL_BUSCADOR_BORME = "https://www.boe.es/diario_borme/busca.php"
URL_BORME_DIARIO = "https://www.boe.es/diario_borme/"
URL_RMC = "https://www.rmc.es/"
URL_REGISTRADORES = "https://www.registradores.org/"


# ---------------------------------------------------------------------------
# Helpers de fecha / normalizacion / recorrido.
# Se copian localmente (en vez de importar de boe.py) para no acoplar modulos.
# ---------------------------------------------------------------------------

_RE_CIF = re.compile(r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$", re.IGNORECASE)


def _fecha_api(fecha: str) -> str | None:
    """'AAAA-MM-DD' o 'DD/MM/AAAA' (o ya 'AAAAMMDD') -> 'AAAAMMDD'."""
    f = fecha.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", f)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", f)
    if m:
        return f"{m.group(3)}{m.group(2)}{m.group(1)}"
    if re.match(r"^\d{8}$", f):
        return f
    return None


def _norm(t: str) -> str:
    """Mayusculas sin tildes, para comparar/filtrar sin sensibilidad a acentos."""
    d = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in d if not unicodedata.combining(c)).upper().strip()


def _iter_items(node):
    """Recorre el arbol del sumario y saca los items (dict con identificador+titulo).

    Sirve para todas las secciones a la vez: los nodos intermedios (diario,
    seccion, apartado, sumario_diario) no cumplen la condicion y se ignoran;
    'sumario_diario' se descarta porque no lleva 'titulo'.
    """
    if isinstance(node, list):
        for x in node:
            yield from _iter_items(x)
    elif isinstance(node, dict):
        if "identificador" in node and "titulo" in node:
            yield node
        else:
            for v in node.values():
                yield from _iter_items(v)


def _seccion_de(identificador: str) -> str:
    """'BORME-A-2026-156-01' -> 'A'. Devuelve '?' si no encaja."""
    m = re.match(r"^BORME-([ABCS])-", identificador or "", re.IGNORECASE)
    return m.group(1).upper() if m else "?"


# ---------------------------------------------------------------------------
# 1) Sumario del BORME de un dia  (AUTOMATIZABLE)
# ---------------------------------------------------------------------------

def sumario_borme(fecha: str, contiene: str = "") -> str:
    """Que se publico en el BORME de un dia. fecha: AAAA-MM-DD o DD/MM/AAAA.

    Devuelve las entradas con su identificador BORME-A/B/C-... y su titulo.
    Con 'contiene' filtra por texto (sin tildes ni mayusculas). Recuerda que en
    la Seccion A el titulo es la PROVINCIA; los nombres de sociedad aparecen en
    la Seccion C (anuncios). Para buscar una empresa por nombre usa
    buscar_empresa_mercantil.
    """
    f = _fecha_api(fecha)
    if not f:
        return f"Fecha no valida: «{fecha}». Usa AAAA-MM-DD o DD/MM/AAAA."
    try:
        d = get_json(f"{API}/borme/sumario/{f}")
    except Exception as e:  # noqa: BLE001
        return (
            f"No pude leer el sumario del BORME de {fecha}: {e} "
            f"(¿fue dia inhabil sin BORME?)."
        )

    sumario = d.get("data", {}).get("sumario", {})
    items = list(_iter_items(sumario.get("diario", sumario)))

    filtro = _norm(contiene) if contiene else ""
    if filtro:
        items = [it for it in items if filtro in _norm(it.get("titulo", ""))]

    if not items:
        return (
            f"Sin resultados en el BORME de {fecha}"
            + (f" con «{contiene}»" if contiene else "")
            + "."
        )

    cab = (
        f"BORME de {fecha}: {len(items)} entradas"
        + (f" con «{contiene}»" if contiene else "")
        + ":"
    )
    lineas = [cab, ""]
    for it in items[:60]:
        ident = it.get("identificador", "?")
        sec = _seccion_de(ident)
        titulo = (it.get("titulo") or "").strip()
        lineas.append(f"• [{sec}] {ident} — {titulo[:180]}")
    if len(items) > 60:
        lineas.append(
            f"... y {len(items) - 60} mas. Afina con 'contiene' (p.ej. una provincia "
            f"en la Seccion A o una denominacion social en la Seccion C)."
        )
    lineas.append(
        "\nSecciones: A=actos inscritos (por provincia) · "
        "B=otros actos del Registro Mercantil · C=anuncios y avisos legales."
    )
    lineas.append("El PDF/HTML de cada entrada esta en boe.es por su identificador BORME-...")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 2) Ficha de una sociedad por nombre o CIF  (HUMANO-EN-EL-BUCLE)
# ---------------------------------------------------------------------------

def buscar_empresa_mercantil(empresa: str) -> str:
    """Ficha de una sociedad por nombre o CIF.

    HONESTIDAD: la API de datos abiertos del BOE indexa el BORME por FECHA, no
    por empresa; no existe un endpoint abierto, barato y estable para buscar una
    sociedad por su nombre. Por eso esto NO simula una busqueda: prepara los
    buscadores OFICIALES para que el usuario complete la consulta (humano en el
    bucle) y explica el alcance del BORME.
    """
    consulta = (empresa or "").strip()
    if not consulta:
        return (
            "Indica el nombre de la sociedad o su CIF. Ejemplos: "
            "'ACTIVO MADECO SL' o 'B12345674'."
        )

    es_cif = bool(_RE_CIF.match(consulta.replace(" ", "")))
    tipo = "CIF" if es_cif else "denominacion social"
    q = quote_plus(consulta)

    lineas = [
        f"Busqueda mercantil de «{consulta}» ({tipo}).",
        "",
        "No hay API abierta del BOE/BORME que busque una sociedad por nombre o CIF "
        "de forma directa (el sumario solo se indexa por fecha). Usa estos buscadores "
        "OFICIALES (humano en el bucle):",
        "",
        "1) Buscador del BORME (anuncios y actos inscritos publicados):",
        f"   {URL_BUSCADOR_BORME}",
        f"   Diario BORME (por dias): {URL_BORME_DIARIO}",
        f"   Sugerencia de texto a pegar en el buscador: {consulta}",
        f"   (enlace directo con el texto codificado: {URL_BUSCADOR_BORME}?dato={q})",
        "",
        "2) Registro Mercantil Central — denominaciones y datos registrales:",
        f"   {URL_RMC}",
        "3) Registradores de Espana — notas simples / informacion mercantil:",
        f"   {URL_REGISTRADORES}",
        "",
        "ALCANCE — que es y que NO es el BORME:",
        "• El BORME es un INDICE de publicidad legal: constituciones, nombramientos "
        "y ceses, ampliaciones/reducciones de capital, convocatorias de junta, "
        "fusiones, disolucion/liquidacion, concursos...",
        "• NO tiene fe publica registral y NO contiene las CUENTAS ANUALES ni la "
        "titularidad real. Para datos con valor certificante (nota simple, "
        "certificacion, cuentas depositadas) hay que acudir al Registro Mercantil "
        "territorial o al Central, servicio de pago y sin API abierta.",
        "",
        "Si conoces la FECHA de publicacion, si es automatizable: usa "
        "sumario_borme(fecha, contiene=\"" + consulta + "\") para localizar la "
        "entrada BORME-C-... (anuncios) de esa sociedad ese dia.",
    ]
    return "\n".join(lineas)
