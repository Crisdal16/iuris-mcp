"""Tribunal Constitucional — busqueda y lectura desde su Buscador de
Jurisprudencia Constitucional (HJ), hj.tribunalconstitucional.es.

No hay API documentada, pero el buscador es un formulario ASP.NET que responde a
HTTP plano sin control anti-bot, y cada resolucion se sirve en HTML ya
seccionado (antecedentes, fundamentos juridicos, fallo, votos particulares,
ficha tecnica y extractos). Verificado en sept. 2026.

Flujo:
  1. GET  /HJ/es/Busqueda/Index  -> cookie + __RequestVerificationToken
  2. POST /HJ/es/Busqueda/Buscar (texto libre, numero/anio, ECLI, tipo, materia,
     fechas) -> redirige a /HJ/es/Resolucion/List (paginable con ?page=N)
  3. GET  /HJ/es/Resolucion/Show/<id> -> HTML con las secciones

La otra via oficial es el BOE (publica todas las STC); la cabecera de cada
resolucion cita su BOE (numero y fecha), y se incluye en la salida.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from common.cendoj_ids import Ecli, normalizar_cita
from common.texto import dir_destino, parrafos_con, slug, texto_de_html, truncar, norm

BASE = "https://hj.tribunalconstitucional.es"
_URL_INDEX = BASE + "/HJ/es/Busqueda/Index"
_URL_BUSCAR = BASE + "/HJ/es/Busqueda/Buscar"
_URL_LIST = BASE + "/HJ/es/Resolucion/List"
_URL_SHOW = BASE + "/HJ/es/Resolucion/Show/{id}"

_HEADERS = {
    "User-Agent": "iuris-mcp/0.1 (servidor MCP juridico de uso profesional propio)",
    "Accept-Language": "es-ES,es;q=0.9",
}
_TIMEOUT = 60.0

try:
    from diskcache import Cache

    _cache: Any = Cache(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "tc"),
                        size_limit=int(1e9))
except Exception:  # pragma: no cover
    _cache = None

# Campo TIPO_BUSQUEDA_LIBRE del formulario
_AMBITO = {"TODO": "0", "PREAMBULO": "1", "ANTECEDENTES": "2", "FUNDAMENTOS": "3",
           "FALLO": "4", "VOTOS": "5", "SINTESIS": "6", "SINTESIS DESCRIPTIVA": "6",
           "SINTESIS ANALITICA": "7"}
_MATERIA = {"CIVIL": "1", "CONTENCIOSO": "2", "CONTENCIOSO-ADMINISTRATIVO": "2",
            "ELECTORAL": "3", "MILITAR": "4", "PARLAMENTARIO": "5", "PENAL": "6",
            "SOCIAL": "8", "LABORAL": "8", "OTROS": "9"}
_TIPO = {"SENTENCIA": "SENTENCIA", "STC": "SENTENCIA", "S": "SENTENCIA",
         "AUTO": "AUTO", "ATC": "AUTO", "A": "AUTO",
         "DECLARACION": "DECLARACION", "DTC": "DECLARACION", "D": "DECLARACION"}

# "STC 31/2010", "ATC 12/2020", "DTC 1/2004"
_RE_CITA_TC = re.compile(r"^(?P<tipo>STC|ATC|DTC)\s*(?P<num>\d+)\s*/\s*(?P<anio>\d{4})$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Sesion y busqueda
# ---------------------------------------------------------------------------

def _sesion() -> tuple[httpx.Client, str]:
    cli = httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=_TIMEOUT)
    r = cli.get(_URL_INDEX)
    r.raise_for_status()
    m = re.search(r'__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    if not m:
        cli.close()
        raise RuntimeError("El buscador del TC no devolvio el token del formulario (¿cambio de sitio?).")
    return cli, m.group(1)


def _fecha(s: str) -> str:
    s = (s or "").strip()
    if "-" in s:
        p = s.split("-")
        if len(p) == 3 and len(p[0]) == 4:
            return f"{p[2]}/{p[1]}/{p[0]}"
    return s


def _parsear_lista(html: str) -> tuple[int | None, list[dict]]:
    t = HTMLParser(html)
    total = None
    m = re.search(r"Todos\s*\((\d[\d\.]*)\)", html)
    if m:
        total = int(m.group(1).replace(".", ""))
    out: list[dict] = []
    for li in t.css("ul#resolution-list li"):
        a = li.css_first('a[href*="Resolucion/Show/"]')
        if a is None:
            continue
        href = a.attributes.get("href", "")
        mid = re.search(r"Show/(\d+)", href)
        if not mid or mid.group(1) == "0":
            continue
        texto = texto_de_html(li)
        titulo = " ".join(a.text().split())
        tipo_proc = _m(r"Tipo de Proceso\n?(.+?)(?:\n|$)", texto)
        sint_d = _m(r"Síntesis Descriptiva\n?(.+?)(?:\nSíntesis|\n\s*$|$)", texto, dotall=True)
        sint_a = _m(r"Síntesis Analítica\n?(.+?)$", texto, dotall=True)
        out.append({
            "id": mid.group(1), "titulo": titulo, "tipo_proceso": tipo_proc,
            "sintesis_descriptiva": sint_d, "sintesis_analitica": sint_a,
            "url": _URL_SHOW.format(id=mid.group(1)),
        })
    # el listado repite cada enlace varias veces: deduplicar por id conservando orden
    vistos: set[str] = set()
    unicos = []
    for r in out:
        if r["id"] not in vistos:
            vistos.add(r["id"])
            unicos.append(r)
    return total, unicos


def _m(patron: str, texto: str, dotall: bool = False) -> str | None:
    r = re.search(patron, texto, re.IGNORECASE | (re.DOTALL if dotall else 0))
    return " ".join(r.group(1).split()) if r else None


def _buscar(cli: httpx.Client, token: str, datos: dict, pagina: int = 1) -> tuple[int | None, list[dict]]:
    d = {"__RequestVerificationToken": token}
    d.update({k: v for k, v in datos.items() if v})
    r = cli.post(_URL_BUSCAR, data=d)
    r.raise_for_status()
    if pagina > 1:
        r = cli.get(_URL_LIST, params={"page": pagina})
        r.raise_for_status()
    return _parsear_lista(r.text)


def _localizar(cli: httpx.Client, token: str, cita: str) -> dict | None:
    """'STC 31/2010' / 'ECLI:ES:TC:2010:31' -> primer resultado (dict) o None."""
    c = " ".join(cita.split())
    m = _RE_CITA_TC.match(c)
    datos: dict = {}
    if m:
        datos = {"NUMERO_RESOLUCION": m.group("num"), "ANNO_RESOLUCION": m.group("anio"),
                 "TIPO_RESOLUCION": _TIPO[m.group("tipo").upper()]}
    else:
        obj = normalizar_cita(c)
        if isinstance(obj, Ecli) and obj.tribunal == "TC":
            datos = {"anno_resolucion_ecli": str(obj.anio), "numero_resolucion_ecli": obj.numero,
                     "TIPO_RESOLUCION_ECLI": "AUTO" if obj.es_auto else "SENTENCIA"}
    if not datos:
        return None
    _, res = _buscar(cli, token, datos)
    return res[0] if res else None


# ---------------------------------------------------------------------------
# Lectura de una resolucion
# ---------------------------------------------------------------------------

_SECCIONES_HTML = [
    ("antecedentes", "#antecedentes-container"),
    ("fundamentos", "#fundamentos-container"),
    ("fallo", "#dictamen-container"),
    ("votos", "#votos-container"),
    ("ficha", "#ficha-tecnica"),
    ("extractos", "#extractos"),
]
_ALIAS_SECCION = {
    "todo": "todo", "completo": "todo", "": "todo",
    "antecedentes": "antecedentes", "fundamentos": "fundamentos",
    "fundamentos juridicos": "fundamentos", "fj": "fundamentos",
    "fallo": "fallo", "dictamen": "fallo", "votos": "votos", "votos particulares": "votos",
    "ficha": "ficha", "ficha tecnica": "ficha", "extractos": "extractos", "sintesis": "extractos",
}


def _leer_show(cli: httpx.Client, id_res: str) -> dict:
    clave = f"show:{id_res}"
    hit = _cache.get(clave) if _cache is not None else None
    if hit:
        return hit
    r = cli.get(_URL_SHOW.format(id=id_res))
    r.raise_for_status()
    t = HTMLParser(r.text)
    h2 = t.css_first("h2")
    titulo = " ".join(h2.text().split()) if h2 else f"Resolucion {id_res}"
    e = t.css_first("label.ecli")
    ecli = e.text(strip=True) if e else None
    secs: dict[str, str] = {}
    for nombre, sel in _SECCIONES_HTML:
        n = t.css_first(sel)
        if n is not None:
            txt = texto_de_html(n)
            if txt:
                secs[nombre] = txt
    doc = {"id": id_res, "titulo": titulo, "ecli": ecli, "secciones": secs,
           "url": _URL_SHOW.format(id=id_res)}
    if _cache is not None and secs:
        _cache.set(clave, doc)
    return doc


def _cabecera(doc: dict) -> str:
    partes = [doc["titulo"]]
    if doc.get("ecli"):
        partes.append(doc["ecli"])
    ficha = doc["secciones"].get("ficha", "")
    org = _m(r"Órgano\n(.+?)\n", ficha)
    pon = _m(r"Ponente\n(.+?)\n", ficha)
    tipo = _m(r"Tipo\n(.+?)\n", ficha)
    extra = [x for x in (org, tipo, (f"Ponente: {pon}" if pon else None)) if x]
    out = " · ".join(partes)
    if extra:
        out += "\n" + " · ".join(extra)
    out += f"\n{doc['url']}"
    return out


def _texto_completo(doc: dict) -> str:
    s = doc["secciones"]
    orden = ["antecedentes", "fundamentos", "fallo", "votos"]
    return "\n\n".join(s[k] for k in orden if k in s) or "\n\n".join(s.values())


def _a_markdown(doc: dict) -> str:
    s = doc["secciones"]
    lineas = [f"# {doc['titulo']}", ""]
    if doc.get("ecli"):
        lineas.append(f"- **ECLI**: {doc['ecli']}")
    lineas.append(f"- **Fuente**: [{doc['url']}]({doc['url']})")
    titulos = [("ficha", "Ficha técnica"), ("extractos", "Extractos / síntesis"),
               ("antecedentes", "Antecedentes"), ("fundamentos", "Fundamentos jurídicos"),
               ("fallo", "Fallo"), ("votos", "Votos particulares")]
    for k, tit in titulos:
        if k in s:
            lineas += ["", "---", "", f"## {tit}", "", s[k]]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# API publica (sync: httpx puro, sin navegador)
# ---------------------------------------------------------------------------

def buscar_tc(
    consulta: str = "",
    ambito: str = "todo",
    numero: str = "",
    anio: str = "",
    ecli: str = "",
    tipo: str = "",
    materia: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    pagina: int = 1,
    maximo: int = 10,
) -> str:
    consulta = " ".join((consulta or "").split())
    cita = consulta if _RE_CITA_TC.match(consulta) else ""
    if not any([consulta, numero, ecli, fecha_desde, fecha_hasta, materia]):
        return "Indica una consulta (texto libre o 'STC 31/2010'), un numero+anio, un ECLI, una materia o fechas."
    datos: dict = {}
    if cita:
        m = _RE_CITA_TC.match(cita)
        datos.update({"NUMERO_RESOLUCION": m.group("num"), "ANNO_RESOLUCION": m.group("anio"),
                      "TIPO_RESOLUCION": _TIPO[m.group("tipo").upper()]})
    elif consulta:
        datos["BUSQUEDA_LIBRE"] = consulta
        datos["TIPO_BUSQUEDA_LIBRE"] = _AMBITO.get(norm(ambito), "0")
    if numero:
        datos["NUMERO_RESOLUCION"] = str(numero).strip()
        if anio:
            datos["ANNO_RESOLUCION"] = str(anio).strip()
    if ecli:
        obj = normalizar_cita(ecli)
        if isinstance(obj, Ecli):
            datos.update({"anno_resolucion_ecli": str(obj.anio), "numero_resolucion_ecli": obj.numero,
                          "TIPO_RESOLUCION_ECLI": "AUTO" if obj.es_auto else "SENTENCIA"})
    if tipo and not cita:
        datos["TIPO_RESOLUCION"] = _TIPO.get(norm(tipo), "")
    if materia:
        datos["MATERIA"] = _MATERIA.get(norm(materia), "")
    if fecha_desde:
        datos["FECHA_DESDE"] = _fecha(fecha_desde)
    if fecha_hasta:
        datos["FECHA_HASTA"] = _fecha(fecha_hasta)

    cli = None
    try:
        cli, token = _sesion()
        total, res = _buscar(cli, token, datos, pagina=max(1, int(pagina or 1)))
    except Exception as e:
        return f"TC: fallo al consultar el buscador ({type(e).__name__}: {e}). Alternativa manual: {_URL_INDEX}"
    finally:
        if cli is not None:
            cli.close()

    res = res[: max(1, min(int(maximo or 10), 50))]
    if not res:
        return f"Sin resultados en el TC para esa busqueda (total: {total or 0})."
    out = [f"TRIBUNAL CONSTITUCIONAL — {total if total is not None else len(res)} resultado(s). "
           f"Pagina {pagina}, mostrando {len(res)}:", ""]
    for i, r in enumerate(res, 1):
        out.append(f"{i}. {r['titulo']}")
        if r.get("tipo_proceso"):
            out.append(f"   {r['tipo_proceso']}")
        if r.get("sintesis_descriptiva"):
            s = r["sintesis_descriptiva"]
            out.append(f"   Sintesis: {s[:300]}{'…' if len(s) > 300 else ''}")
        if r.get("sintesis_analitica"):
            s = r["sintesis_analitica"]
            out.append(f"   Doctrina: {s[:300]}{'…' if len(s) > 300 else ''}")
        out.append(f"   id: {r['id']} · {r['url']}")
        out.append("")
    if total and total > pagina * 10:
        out.append(f"Hay mas: repite con pagina={pagina + 1}.")
    out.append("Texto: `leer_tc` con el id (o con 'STC 31/2010' / ECLI). seccion='fallo' o "
               "'fundamentos' para acotar; palabras_clave para los pasajes relevantes.")
    return "\n".join(out)


def leer_tc(
    referencia: str,
    seccion: str = "todo",
    palabras_clave: str = "",
    guardar_md: bool = False,
    ruta: str = "",
    max_chars: int = 45000,
) -> str:
    ref = " ".join((referencia or "").split())
    if not ref:
        return "Indica el id (de buscar_tc), la cita ('STC 31/2010', 'ATC 12/2020') o el ECLI (ECLI:ES:TC:2010:31)."
    cli = None
    try:
        cli, token = _sesion()
        if ref.isdigit():
            id_res = ref
        else:
            m = re.search(r"Resolucion/Show/(\d+)", ref)
            if m:
                id_res = m.group(1)
            else:
                hit = _localizar(cli, token, ref)
                if not hit:
                    return f"No encuentro «{ref}» en el buscador del TC. Revisa la cita."
                id_res = hit["id"]
        doc = _leer_show(cli, id_res)
    except Exception as e:
        return f"TC: fallo al obtener la resolucion ({type(e).__name__}: {e})."
    finally:
        if cli is not None:
            cli.close()

    secs = doc["secciones"]
    if not secs:
        return f"La pagina {doc['url']} no contiene secciones reconocibles (¿cambio de sitio?)."
    completo = _texto_completo(doc)

    guardados = []
    if guardar_md:
        d = dir_destino(ruta, os.path.join(os.path.dirname(os.path.dirname(__file__)), "descargas"))
        etiqueta = slug(doc.get("ecli") or doc["titulo"][:40])
        p = os.path.join(d, f"{etiqueta}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_a_markdown(doc))
        guardados.append(p)

    etiqueta_parte = ""
    if palabras_clave.strip():
        ps, modo = parrafos_con(completo, palabras_clave)
        cuerpo = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(ps, 1)) if ps else \
            f"Ningun parrafo contiene «{palabras_clave}»."
        etiqueta_parte = f"Parrafos con «{palabras_clave}» ({len(ps)})"
        if modo == "alguna":
            etiqueta_parte += " — AVISO: ninguno contiene TODAS las palabras; se muestran los que contienen alguna."
    else:
        clave = _ALIAS_SECCION.get((seccion or "todo").strip().lower())
        if clave is None:
            cuerpo = (f"Seccion «{seccion}» no reconocida (usa: fallo, fundamentos, antecedentes, "
                      f"votos, ficha, extractos, todo). Devuelvo el texto completo.\n\n{completo}")
        elif clave == "todo":
            cuerpo = completo
        elif clave in secs:
            cuerpo = secs[clave]
            etiqueta_parte = f"Seccion: {clave.upper()}"
        else:
            cuerpo = (f"Esta resolucion no tiene seccion «{clave}». Disponibles: "
                      f"{', '.join(secs)}. Devuelvo el texto completo.\n\n{completo}")

    partes = [_cabecera(doc)]
    if etiqueta_parte:
        partes.append(etiqueta_parte)
    if guardados:
        partes.append("Guardado en:\n  " + "\n  ".join(guardados))
    partes.append(truncar(cuerpo, max_chars, len(completo),
                          "Sube max_chars, usa seccion='fallo'/'fundamentos' o palabras_clave, "
                          "o guardar_md=True para el fichero completo."))
    return "\n\n".join(p for p in partes if p)
