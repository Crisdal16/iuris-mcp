"""TJUE y Tribunal General — busqueda y lectura via CELLAR, la API publica
oficial de la Oficina de Publicaciones de la UE (publications.europa.eu).

EUR-Lex y CURIA aplican control anti-bot al acceso automatizado, pero CELLAR es
precisamente la API abierta que hay detras de EUR-Lex:

  • SPARQL:  http://publications.europa.eu/webapi/rdf/sparql
             (localizar por ECLI, por asunto o por palabras del titulo)
  • Documento por CELEX con negociacion de contenido:
             http://publications.europa.eu/resource/celex/<CELEX>
             Accept: application/xhtml+xml, Accept-Language: es  -> texto en ESPANOL

CELEX de jurisprudencia UE: 6 + anio(4) + tipo + numero(4)
    62018CJ0311  sentencia del Tribunal de Justicia, asunto C-311/18
    62016TJ0778  sentencia del Tribunal General, asunto T-778/16
    62018CC0311  conclusiones del Abogado General en C-311/18
    62018CO0311  auto del Tribunal de Justicia
    ..._RES      resumen (se descarta)
Verificado en sept. 2026.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from common.cendoj_ids import Ecli, normalizar_cita
from common.texto import dir_destino, parrafos_con, slug, texto_de_html, truncar

SPARQL = "http://publications.europa.eu/webapi/rdf/sparql"
CELLAR = "http://publications.europa.eu/resource/celex/{celex}"
EURLEX = "https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{celex}"
CURIA = "https://curia.europa.eu/juris/liste.jsf?num={asunto}&language=es"

_HEADERS = {"User-Agent": "iuris-mcp/0.1 (servidor MCP juridico de uso profesional propio)"}
_TIMEOUT = 90.0
_PREFIX = "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\n"
_LANG_ES = "<http://publications.europa.eu/resource/authority/language/SPA>"

try:
    from diskcache import Cache

    _cache: Any = Cache(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "tjue"),
                        size_limit=int(1e9))
except Exception:  # pragma: no cover
    _cache = None

_RE_CELEX = re.compile(r"^6(?P<anio>\d{4})(?P<tipo>[A-Z]{2})(?P<num>\d{4})$")
_RE_ASUNTO = re.compile(r"^(?P<sala>[CT])\s*-\s*(?P<num>\d{1,4})\s*/\s*(?P<anio>\d{2,4})", re.IGNORECASE)

_TIPO_DOC = {
    "sentencia": ("CJ", "TJ"), "conclusiones": ("CC",), "auto": ("CO", "TO"),
}
_NOMBRE_TIPO = {"CJ": "Sentencia del Tribunal de Justicia", "TJ": "Sentencia del Tribunal General",
                "CC": "Conclusiones del Abogado General", "CO": "Auto del Tribunal de Justicia",
                "TO": "Auto del Tribunal General", "CA": "Resumen"}


def _anio4(a: str) -> str:
    if len(a) == 4:
        return a
    n = int(a)
    return ("19" if n >= 50 else "20") + a.zfill(2)


def a_celex_candidatos(referencia: str, tipo: str = "sentencia") -> list[str]:
    """'C-311/18' -> ['62018CJ0311']; 'T-778/16' -> ['62016TJ0778']; CELEX directo."""
    r = " ".join(referencia.strip().split()).upper()
    if _RE_CELEX.match(r):
        return [r]
    m = _RE_ASUNTO.match(r)
    if not m:
        return []
    anio, num, sala = _anio4(m.group("anio")), m.group("num").zfill(4), m.group("sala").upper()
    tipos = _TIPO_DOC.get((tipo or "sentencia").lower(), ("CJ", "TJ"))
    # C- -> Tribunal de Justicia (CJ/CC/CO); T- -> Tribunal General (TJ/TO)
    orden = [t for t in tipos if (t.startswith("C") if sala == "C" else t.startswith("T"))] or list(tipos)
    return [f"6{anio}{t}{num}" for t in orden]


# ---------------------------------------------------------------------------
# SPARQL
# ---------------------------------------------------------------------------

def _sparql(q: str) -> list[dict]:
    r = httpx.get(SPARQL, params={"query": _PREFIX + q},
                  headers={**_HEADERS, "Accept": "application/sparql-results+json"}, timeout=_TIMEOUT)
    r.raise_for_status()
    filas = r.json()["results"]["bindings"]
    return [{k: v["value"] for k, v in b.items()} for b in filas]


def celex_por_ecli(ecli: str) -> list[dict]:
    q = f'''SELECT DISTINCT ?celex ?date WHERE {{
      ?w cdm:case-law_ecli ?ecli ; cdm:resource_legal_id_celex ?celex .
      OPTIONAL {{ ?w cdm:work_date_document ?date }}
      FILTER(str(?ecli) = "{ecli}") }}'''
    return [f for f in _sparql(q) if not f["celex"].endswith("_RES")]


def buscar_titulos(palabras: list[str], desde: str = "", hasta: str = "",
                   tribunal: str = "", maximo: int = 10) -> list[dict]:
    filtros = " && ".join(f'CONTAINS(LCASE(str(?title)), "{p.lower()}")' for p in palabras)
    tipos = {"": "CJ|TJ", "tjue": "CJ", "justicia": "CJ", "general": "TJ", "tg": "TJ"}.get(tribunal.lower(), "CJ|TJ")
    fechas = ""
    if desde:
        fechas += f' && str(?date) >= "{desde}"'
    if hasta:
        fechas += f' && str(?date) <= "{hasta}"'
    q = f'''SELECT ?celex ?ecli ?date ?title WHERE {{
      ?w cdm:resource_legal_id_celex ?celex ; cdm:work_date_document ?date .
      OPTIONAL {{ ?w cdm:case-law_ecli ?ecli }}
      ?exp cdm:expression_belongs_to_work ?w ;
           cdm:expression_uses_language {_LANG_ES} ;
           cdm:expression_title ?title .
      FILTER(REGEX(str(?celex), "^6[0-9]{{4}}({tipos})[0-9]{{4}}$") && {filtros}{fechas})
    }} ORDER BY DESC(?date) LIMIT {int(maximo)}'''
    return _sparql(q)


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------

def _descargar(celex: str) -> str | None:
    clave = f"txt:{celex}"
    hit = _cache.get(clave) if _cache is not None else None
    if hit:
        return hit
    # Los documentos recientes se sirven en XHTML; los antiguos (p.ej. la
    # Directiva 93/13/CEE) solo en HTML: 404 con xhtml, 200 con text/html.
    for accept in ("application/xhtml+xml", "text/html"):
        r = httpx.get(CELLAR.format(celex=celex),
                      headers={**_HEADERS, "Accept": accept, "Accept-Language": "es"},
                      follow_redirects=True, timeout=_TIMEOUT)
        if r.status_code == 200 and r.content:
            break
    else:
        return None
    t = HTMLParser(r.text)
    texto = texto_de_html(t.body if t.body else t.root)
    # Marcas de nota al pie que EUR-Lex renderiza como lineas sueltas: "(", "*1", ")"
    texto = re.sub(r"\s*\(\n\*\d+\n\)", "", texto)
    texto = re.sub(r"\n\*\d+\n", "\n", texto)
    if _cache is not None and texto:
        _cache.set(clave, texto)
    return texto


def _resolver(referencia: str, tipo: str) -> tuple[str | None, str]:
    """Devuelve (celex, nota). Acepta CELEX, asunto (C-311/18) o ECLI (ECLI:EU:C:2020:559)."""
    ref = " ".join(referencia.strip().split())
    obj = normalizar_cita(ref)
    if isinstance(obj, Ecli) and obj.pais == "EU":
        cands = celex_por_ecli(str(obj))
        tipos = _TIPO_DOC.get((tipo or "sentencia").lower(), ("CJ", "TJ"))
        pref = [c["celex"] for c in cands if c["celex"][5:7] in tipos]
        if pref:
            return pref[0], f"ECLI {obj} → CELEX {pref[0]}"
        if cands:
            c = cands[0]["celex"]
            return c, (f"ECLI {obj} → CELEX {c} ({_NOMBRE_TIPO.get(c[5:7], c[5:7])}). "
                       f"Nota: el ECLI identifica ese documento; para '{tipo}' usa el asunto (C-nnn/aa).")
        return None, f"ECLI {obj} sin CELEX en CELLAR"
    for celex in a_celex_candidatos(ref, tipo):
        r = httpx.head(CELLAR.format(celex=celex), headers={**_HEADERS, "Accept": "application/xhtml+xml",
                                                            "Accept-Language": "es"},
                       follow_redirects=True, timeout=_TIMEOUT)
        if r.status_code == 200:
            return celex, f"{ref} → CELEX {celex}"
    return None, f"No hay documento en CELLAR para «{ref}» ({tipo})."


def _fallo(texto: str) -> str | None:
    i = texto.find("En virtud de todo lo expuesto")
    return texto[i:].strip() if i >= 0 else None


def _cabecera(texto: str, celex: str) -> str:
    lineas = [l for l in texto.splitlines() if l.strip()]
    tit = " ".join(lineas[:2]) if lineas else celex
    m = re.search(r"«[^»]{10,}»", texto[:3000])
    asunto = re.search(r"asuntos? (?:acumulados )?[CT]-\d+/\d+(?: y [CT]-\d+/\d+)*", texto[:5000], re.IGNORECASE)
    partes = [f"CELEX {celex}", _NOMBRE_TIPO.get(celex[5:7], celex[5:7]), tit[:120]]
    if asunto:
        partes.append(asunto.group(0))
    out = " · ".join(partes)
    if m:
        out += "\n" + m.group(0)[:400]
    out += f"\n{EURLEX.format(celex=celex)}"
    return out


# ---------------------------------------------------------------------------
# API publica (sync: httpx puro)
# ---------------------------------------------------------------------------

def buscar_tjue(consulta: str = "", desde: str = "", hasta: str = "",
                tribunal: str = "", maximo: int = 10) -> str:
    consulta = " ".join((consulta or "").split())
    if not consulta:
        return "Indica palabras clave (p.ej. 'cláusulas abusivas consumidor'), un asunto (C-311/18) o un ECLI (ECLI:EU:C:2020:559)."
    # Asunto o ECLI directo -> resolver
    obj = normalizar_cita(consulta)
    if _RE_ASUNTO.match(consulta.upper()) or (isinstance(obj, Ecli) and obj.pais == "EU"):
        try:
            if isinstance(obj, Ecli):
                filas = celex_por_ecli(str(obj))
            else:
                filas = []
                for tipo in ("sentencia", "conclusiones", "auto"):
                    celex, _ = _resolver(consulta, tipo)
                    if celex:
                        filas.append({"celex": celex})
        except Exception as e:
            return f"TJUE: fallo consultando CELLAR ({type(e).__name__}: {e}). Manual: {CURIA.format(asunto=consulta)}"
        if not filas:
            return f"No encuentro documentos para «{consulta}» en CELLAR. Manual: {CURIA.format(asunto=consulta)}"
        out = [f"TJUE — documentos de «{consulta}»:", ""]
        for f in filas:
            c = f["celex"]
            out.append(f"• {c} — {_NOMBRE_TIPO.get(c[5:7], c[5:7])}" + (f" ({f['date']})" if f.get("date") else ""))
        out.append("")
        out.append("Texto: `leer_tjue` con el CELEX, el asunto o el ECLI (tipo='conclusiones' para las del AG).")
        return "\n".join(out)

    palabras = [p for p in re.split(r"[,\s]+", consulta) if len(p) > 2]
    try:
        filas = buscar_titulos(palabras, desde=desde, hasta=hasta, tribunal=tribunal,
                               maximo=max(1, min(int(maximo or 10), 30)))
    except Exception as e:
        return f"TJUE: fallo consultando CELLAR/SPARQL ({type(e).__name__}: {e})."
    if not filas:
        return (f"Sin sentencias cuyo titulo (en espanol) contenga «{consulta}». La busqueda es por "
                f"palabras del TITULO (materia/descriptores), no del texto: prueba con menos palabras "
                f"o terminos mas genericos, con tildes ('cláusulas abusivas').")
    out = [f"TJUE / Tribunal General — {len(filas)} sentencia(s) (mas recientes primero):", ""]
    for i, f in enumerate(filas, 1):
        tit = f.get("title", "")
        asunto = re.search(r"Asuntos? (?:acumulados )?[CT]-\d+/\d+(?: y [CT]-\d+/\d+)*", tit)
        cab = " ".join(x for x in (f.get("ecli"), f.get("date"), asunto.group(0) if asunto else None) if x)
        out.append(f"{i}. {cab}")
        out.append(f"   {tit.split('#')[0][:350]}")
        out.append(f"   CELEX: {f['celex']}")
        out.append("")
    out.append("Texto: `leer_tjue` con el CELEX o el ECLI. seccion='fallo' devuelve solo la parte dispositiva.")
    return "\n".join(out)


def leer_tjue(referencia: str, tipo: str = "sentencia", seccion: str = "todo",
              palabras_clave: str = "", guardar_md: bool = False, ruta: str = "",
              max_chars: int = 45000) -> str:
    ref = " ".join((referencia or "").split())
    if not ref:
        return "Indica el asunto (C-311/18), el ECLI (ECLI:EU:C:2020:559) o el CELEX (62018CJ0311)."
    try:
        celex, nota = _resolver(ref, tipo)
        if not celex:
            return f"TJUE: {nota} Manual: {CURIA.format(asunto=ref)}"
        texto = _descargar(celex)
    except Exception as e:
        return f"TJUE: fallo al obtener el documento ({type(e).__name__}: {e})."
    if not texto:
        return f"CELLAR no devolvio texto para {celex}."

    guardados = []
    if guardar_md:
        try:
            d = dir_destino(ruta, os.path.join(os.path.dirname(os.path.dirname(__file__)), "descargas"))
            p = os.path.join(d, f"{slug(celex)}.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# {celex}\n\n- **Fuente**: {EURLEX.format(celex=celex)}\n\n---\n\n{texto}")
            guardados.append(p)
        except (ValueError, OSError) as e:
            guardados.append(f"NO GUARDADO: {e}")

    etiqueta_parte = ""
    if palabras_clave.strip():
        ps, modo = parrafos_con(texto, palabras_clave)
        cuerpo = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(ps, 1)) if ps else \
            f"Ningun parrafo contiene «{palabras_clave}»."
        etiqueta_parte = f"Parrafos con «{palabras_clave}» ({len(ps)})"
        if modo == "alguna":
            etiqueta_parte += " — AVISO: ninguno contiene TODAS las palabras; se muestran los que contienen alguna."
    elif (seccion or "todo").strip().lower() in ("fallo", "parte dispositiva", "declara"):
        f = _fallo(texto)
        cuerpo = f or f"No localizo la formula 'En virtud de todo lo expuesto'. Devuelvo el texto completo.\n\n{texto}"
        etiqueta_parte = "Seccion: FALLO (parte dispositiva)" if f else ""
    else:
        cuerpo = texto

    partes = [_cabecera(texto, celex), nota]
    if etiqueta_parte:
        partes.append(etiqueta_parte)
    if guardados:
        partes.append("Guardado en:\n  " + "\n  ".join(guardados))
    partes.append(truncar(cuerpo, max_chars, len(texto),
                          "Sube max_chars, usa seccion='fallo' o palabras_clave, o guardar_md=True.",
                          titulo=f"TJUE {celex}"))
    return "\n\n".join(p for p in partes if p)
