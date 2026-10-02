"""TEAC/TEAR — doctrina de los Tribunales Economico-Administrativos.

Fuente: base de datos oficial DYCTEA (Doctrina y Criterios de los TEA) de la
Secretaria de Estado de Hacienda
  https://serviciostelematicosext.hacienda.gob.es/TEAC/DYCTEA/

VIABILIDAD (verificada con peticiones reales):
  - Sin robots.txt (404) y sin captcha ni login.
  - Aunque el formulario es ASP.NET WebForms (postback con __VIEWSTATE), el sitio
    expone ADEMAS rutas GET limpias que evitan por completo el viewstate:
      criterios.aspx?s=1&rs=&rn=&ra=&fd=&fh=&u=&n=&p=&c1=&c2=&c3=&tc=&tr=&tp=&tf=&c=0&pg=1
          -> HTML con la lista de criterios (doctrina).
      criterio.aspx?id=<ID>        -> detalle de un criterio (asunto + texto).
      textoresolucion.aspx?id=<ID> -> texto integro de la resolucion (iframe).
    Los parametros: rs/rn/ra = nº de reclamacion (sede/numero/anio), fd/fh =
    fechas, u = unidad (organo), tp = todas las palabras, tf = frase exacta,
    c = tipo de criterio, pg = pagina. El id de resultado tiene forma
    '00/06291/2024/00/0/1' (los tres primeros grupos son el nº RG).

  - La cadena TLS de este dominio SI valida, y no exige cabeceras especiales, de
    modo que aqui SI se usa el cliente comun common.http (a diferencia de la DGT).

Todas las funciones devuelven texto legible en espanol.
"""

from __future__ import annotations

import re

import httpx

from common.http import describir_error, get

BASE = "https://serviciostelematicosext.hacienda.gob.es/TEAC/DYCTEA/"
BUSCADOR_URL = BASE

# Unidad resolutoria (parametro 'u') -> codigo oficial del desplegable ddlUnidad.
ORGANOS: dict[str, str] = {
    "TEAC": "00",
    "SALA DESCONCENTRADA DE ALICANTE": "35",
    "SALA DESCONCENTRADA DE GRANADA": "13",
    "SALA DESCONCENTRADA DE TENERIFE": "19",
    "TEAR DE ANDALUCIA": "12",
    "TEAR DE ARAGON": "15",
    "TEAR DE ASTURIAS": "16",
    "TEAR DE BALEARES": "17",
    "TEAR DE CANARIAS": "18",
    "TEAR DE CANTABRIA": "20",
    "TEAR DE CASTILLA Y LEON": "22",
    "TEAR DE CASTILLA-LA MANCHA": "21",
    "TEAR DE CATALUNA": "24",
    "TEAR DE EXTREMADURA": "25",
    "TEAR DE GALICIA": "26",
    "TEAR DE LA RIOJA": "27",
    "TEAR DE MADRID": "28",
    "TEAR DE MURCIA": "29",
    "TEAR DE NAVARRA": "30",
    "TEAR DE VALENCIA": "32",
    "TEAR DEL PAIS VASCO": "31",
}

# Alias cortos por comunidad/provincia -> nombre canonico del organo.
_ALIAS = {
    "ANDALUCIA": "TEAR DE ANDALUCIA", "ARAGON": "TEAR DE ARAGON",
    "ASTURIAS": "TEAR DE ASTURIAS", "BALEARES": "TEAR DE BALEARES",
    "CANARIAS": "TEAR DE CANARIAS", "CANTABRIA": "TEAR DE CANTABRIA",
    "CASTILLA Y LEON": "TEAR DE CASTILLA Y LEON",
    "CASTILLA-LA MANCHA": "TEAR DE CASTILLA-LA MANCHA",
    "CATALUNA": "TEAR DE CATALUNA", "CATALUNYA": "TEAR DE CATALUNA",
    "EXTREMADURA": "TEAR DE EXTREMADURA", "GALICIA": "TEAR DE GALICIA",
    "LA RIOJA": "TEAR DE LA RIOJA", "RIOJA": "TEAR DE LA RIOJA",
    "MADRID": "TEAR DE MADRID", "MURCIA": "TEAR DE MURCIA",
    "NAVARRA": "TEAR DE NAVARRA", "VALENCIA": "TEAR DE VALENCIA",
    "COMUNIDAD VALENCIANA": "TEAR DE VALENCIA",
    "PAIS VASCO": "TEAR DEL PAIS VASCO", "EUSKADI": "TEAR DEL PAIS VASCO",
}

_TIMEOUT = 60.0
_RE_RG = re.compile(r"(?:(\d{1,2})/)?(\d{3,6})/(\d{4})")


def _sin_tildes(t: str) -> str:
    import unicodedata
    d = unicodedata.normalize("NFKD", t)
    return "".join(c for c in d if not unicodedata.combining(c))


def _codigo_organo(organo: str) -> str:
    """'TEAC' / 'TEAR Murcia' / 'Murcia' -> codigo del desplegable (o '')."""
    if not organo:
        return ""
    n = " ".join(_sin_tildes(organo).upper().split())
    if n in ORGANOS:
        return ORGANOS[n]
    if n in _ALIAS:
        return ORGANOS[_ALIAS[n]]
    # 'TEAR MURCIA' -> 'TEAR DE MURCIA'
    n2 = n.replace("TEAR ", "TEAR DE ").replace("DE DE ", "DE ")
    if n2 in ORGANOS:
        return ORGANOS[n2]
    # ultimo intento: por la parte de comunidad
    for alias, canon in _ALIAS.items():
        if alias in n:
            return ORGANOS[canon]
    return ""


def _partir_rg(numero_rg: str) -> tuple[str, str, str] | None:
    """'00/06291/2024' o '06291/2024' -> (sede, numero, anio)."""
    m = _RE_RG.search(numero_rg or "")
    if not m:
        return None
    sede = m.group(1) or "00"
    return sede.zfill(2), m.group(2), m.group(3)


def _params(rs="", rn="", ra="", fd="", fh="", u="", tp="", tf="",
            pg=1) -> dict:
    return {"s": "1", "rs": rs, "rn": rn, "ra": ra, "fd": fd, "fh": fh,
            "u": u, "n": "", "p": "", "c1": "", "c2": "", "c3": "",
            "tc": "", "tr": "", "tp": tp, "tf": tf, "c": "0", "pg": str(pg)}


def _get(ruta: str, params: dict) -> str:
    r = get(BASE + ruta, accept="text/html", params=params, timeout=_TIMEOUT)
    return r.text


def _fecha(f: str) -> str:
    """Fecha a dd/mm/aaaa (formato del buscador)."""
    f = (f or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", f)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return f


def _parsear_lista(html: str) -> tuple[int | None, list[dict]]:
    """De criterios.aspx a (total, [ {id, titulo, rg, asunto} ])."""
    from selectolax.parser import HTMLParser
    doc = HTMLParser(html)
    total = None
    m = re.search(r"([\d.]+)\s+resultados", html)
    if m:
        total = int(m.group(1).replace(".", ""))
    filas: list[dict] = []
    for li in doc.css("li.resultadoCriterio"):
        a = li.css_first("span.resultadoCriterioTitulo a")
        if not a:
            continue
        href = a.attributes.get("href", "")
        mid = re.search(r"id=([^&]+)", href)
        titulo = " ".join(a.text().split())
        mrg = re.search(r"resoluci[oó]n\s+(\d{1,2}/\d{3,6}/\d{4})", titulo)
        texto_node = li.css_first("span.resultadoCriterioTexto")
        filas.append({
            "id": mid.group(1) if mid else "",
            "titulo": titulo,
            "rg": mrg.group(1) if mrg else "",
            "asunto": " ".join((texto_node.text() if texto_node else "").split()),
        })
    return total, filas


def buscar_doctrina_teac(consulta: str = "", frase: str = "", numero_rg: str = "",
                         organo: str = "TEAC", desde: str = "", hasta: str = "",
                         maximo: int = 10) -> str:
    """Busca doctrina y criterios de los TEA (TEAC/TEAR) en la base DYCTEA.

    Parametros (opcionales, se combinan):
      consulta  -> todas estas palabras en el texto.
      frase     -> frase exacta.
      numero_rg -> nº de reclamacion, p.ej. '00/06291/2024'.
      organo    -> 'TEAC' (def.), 'TEAR Murcia', 'Madrid'... o '' para todos.
      desde/hasta -> fecha de la resolucion (aaaa-mm-dd o dd/mm/aaaa).
      maximo    -> maximo de criterios a mostrar.
    """
    if not any([consulta.strip(), frase.strip(), numero_rg.strip()]):
        return ("Indica al menos texto (consulta o frase) o un numero de "
                "reclamacion.\nBuscador oficial DYCTEA: " + BUSCADOR_URL)

    maximo = max(1, min(int(maximo or 10), 50))
    rs = rn = ra = ""
    if numero_rg.strip():
        p = _partir_rg(numero_rg)
        if not p:
            return f"'{numero_rg}' no parece un numero de reclamacion (tipo '00/06291/2024')."
        rs, rn, ra = p

    u = _codigo_organo(organo)
    aviso_org = ""
    if organo.strip() and not u:
        aviso_org = f"\n(No reconoci el organo '{organo}'; busco en todos.)"

    params = _params(rs=rs, rn=rn, ra=ra, fd=_fecha(desde), fh=_fecha(hasta),
                     u=u, tp=consulta.strip(), tf=frase.strip(), pg=1)
    try:
        html = _get("criterios.aspx", params)
    except httpx.HTTPError as e:
        return (f"No se pudo consultar DYCTEA ({describir_error(e)}).\n"
                f"Abrelo a mano: {BUSCADOR_URL}")

    total, filas = _parsear_lista(html)
    filtros = []
    if consulta.strip():
        filtros.append(f'palabras "{consulta.strip()}"')
    if frase.strip():
        filtros.append(f'frase "{frase.strip()}"')
    if numero_rg.strip():
        filtros.append(f"RG {numero_rg.strip()}")
    if organo.strip():
        filtros.append(f"organo {organo.strip()}")
    cab = "Doctrina TEA (DYCTEA) — " + "; ".join(filtros) + aviso_org

    if not filas:
        return cab + "\n\nSin resultados.\nBuscador oficial: " + BUSCADOR_URL

    partes = [cab, ""]
    if total is not None:
        extra = " (solo se listan los primeros 100 en el buscador)" if total > 100 else ""
        partes.append(f"{total} resultados{extra}. Muestro {min(maximo, len(filas))}:")
    for f in filas[:maximo]:
        linea = f"\n· {f['titulo']}"
        if f["asunto"]:
            linea += f"\n    {f['asunto'][:300]}"
        partes.append(linea)
    partes.append(f"\nTexto integro: leer_resolucion_teac('{filas[0]['rg'] or '00/xxxxx/aaaa'}').\n"
                  f"Buscador oficial: {BUSCADOR_URL}")
    return "\n".join(partes)


def _parsear_criterio(html: str) -> dict:
    """De criterio.aspx a un dict con los campos del criterio."""
    from selectolax.parser import HTMLParser
    doc = HTMLParser(html)
    out: dict[str, str] = {}
    mapa = {
        "criterioDatosTitulo": "titulo",
        "criterioDatosCalificacion": "calificacion",
        "criterioDatosUnidad": "unidad",
        "criterioDatosFecha": "fecha",
        "criterioDatosAsunto": "asunto",
        "criterioDatosContenido": "criterio",
        "criterioDatosNormativa": "normativa",
    }
    for div_id, clave in mapa.items():
        node = doc.css_first(f"#{div_id}")
        if node:
            txt = "\n".join(l.rstrip() for l in node.text(separator="\n").splitlines()
                            if l.strip())
            out[clave] = re.sub(r"\n{3,}", "\n\n", txt).strip()
    if not out:  # por si cambia el maquetado, cae a todo el contenido
        cont = doc.css_first("#criterioContenido") or doc.css_first("body")
        if cont:
            out["criterio"] = " ".join(cont.text().split())
    return out


def leer_resolucion_teac(numero_rg: str) -> str:
    """Doctrina de una resolucion TEA por su nº de reclamacion ('00/06291/2024').

    Una resolucion puede fijar varios criterios; se listan todos, con el texto
    integro disponible en la URL de textoresolucion.aspx que se indica.
    """
    numero_rg = (numero_rg or "").strip()
    if not numero_rg:
        return "Indica el numero de reclamacion (p.ej. '00/06291/2024')."
    p = _partir_rg(numero_rg)
    if not p:
        return f"'{numero_rg}' no parece un numero de reclamacion (tipo '00/06291/2024')."
    rs, rn, ra = p

    try:
        html = _get("criterios.aspx", _params(rs=rs, rn=rn, ra=ra))
        total, filas = _parsear_lista(html)
        if not filas:
            return (f"No encuentro la resolucion {rs}/{rn}/{ra} en DYCTEA.\n"
                    f"Compruebala a mano: {BUSCADOR_URL}")
        bloques: list[str] = []
        vistos: set[str] = set()
        for f in filas:
            if not f["id"] or f["id"] in vistos:
                continue
            vistos.add(f["id"])
            det = _parsear_criterio(_get("criterio.aspx", {"id": f["id"]}))
            campos = []
            for clave in ("titulo", "calificacion", "unidad", "fecha", "asunto",
                          "normativa", "criterio"):
                if det.get(clave):
                    campos.append(det[clave])
            texto_url = BASE + "textoresolucion.aspx?id=" + f["id"]
            bloques.append("\n".join(campos) +
                           f"\n\nTexto integro de la resolucion: {texto_url}")
    except httpx.HTTPError as e:
        return (f"No se pudo leer la resolucion {numero_rg} ({describir_error(e)}).\n"
                f"Abrela a mano: {BUSCADOR_URL}")

    cabecera = f"TEA (DYCTEA) — Resolucion {rs}/{rn}/{ra}"
    return cabecera + "\n\n" + ("\n\n" + "-" * 60 + "\n\n").join(bloques)
