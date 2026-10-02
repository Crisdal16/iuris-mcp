"""BOE — legislacion consolidada y sumario, via la API OFICIAL de datos abiertos.

Endpoints (https://www.boe.es/datosabiertos/api):
  /legislacion-consolidada/id/{BOE-A}/texto/indice          -> JSON, lista de bloques
  /legislacion-consolidada/id/{BOE-A}/texto/bloque/{idbloq}  -> XML, texto del bloque
  /boe/sumario/{AAAAMMDD}                                     -> JSON, sumario del dia

Sin captcha, sin login, pensado para reutilizacion. El texto de cada articulo
llega ya como version VIGENTE con su fecha_vigencia y la norma que la dio.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET

from common.http import get_json, get_xml

API = "https://www.boe.es/datosabiertos/api"

# ---------------------------------------------------------------------------
# Siglas / nombres comunes -> identificador BOE de la norma consolidada.
# Verificados: LEC (funciona), CC (BOE-A-1889-4763, confirmado). El resto son
# los IDs oficiales de cada norma. Si falta una, el usuario puede pasar el
# BOE-A directamente o el numero de ley.
# ---------------------------------------------------------------------------

LEYES: dict[str, str] = {
    "CE": "BOE-A-1978-31229",          # Constitucion
    "CC": "BOE-A-1889-4763",           # Codigo Civil
    "CCOM": "BOE-A-1885-6627",         # Codigo de Comercio
    "CP": "BOE-A-1995-25444",          # Codigo Penal
    "LEC": "BOE-A-2000-323",           # Ley de Enjuiciamiento Civil
    "LECRIM": "BOE-A-1882-6036",       # Ley de Enjuiciamiento Criminal
    "LOPJ": "BOE-A-1985-12666",        # Ley Organica del Poder Judicial
    "ET": "BOE-A-2015-11430",          # Estatuto de los Trabajadores
    "LGT": "BOE-A-2003-23186",         # Ley General Tributaria
    "LPAC": "BOE-A-2015-10565",        # Procedimiento Administrativo Comun
    "LRJSP": "BOE-A-2015-10566",       # Regimen Juridico del Sector Publico
    "LJCA": "BOE-A-1998-16718",        # Jurisdiccion Contencioso-administrativa
    "LRJS": "BOE-A-2011-15936",        # Jurisdiccion Social
    "LAU": "BOE-A-1994-26003",         # Arrendamientos Urbanos
    "LPH": "BOE-A-1960-10906",         # Propiedad Horizontal
    "LSC": "BOE-A-2010-10544",         # Sociedades de Capital
    "LH": "BOE-A-1946-2453",           # Ley Hipotecaria
    "LC": "BOE-A-2020-4859",           # Ley Concursal (TR)
    "LIVA": "BOE-A-1992-28740",        # IVA
    "LIRPF": "BOE-A-2006-20764",       # IRPF
    "LIS": "BOE-A-2014-12328",         # Impuesto sobre Sociedades
    "LOTC": "BOE-A-1979-23709",        # Ley Organica del Tribunal Constitucional
    # Verificados 2026-10-02 con resolver_por_numero (API, rango + ambito estatal):
    "LOPDGDD": "BOE-A-2018-16673",     # LO 3/2018 Proteccion de Datos
    "LGSS": "BOE-A-2015-11724",        # RDLeg 8/2015 Seguridad Social
    "TRLGDCU": "BOE-A-2007-20555",     # RDLeg 1/2007 Consumidores y Usuarios
    "LGDCU": "BOE-A-2007-20555",
    "LCSP": "BOE-A-2017-12902",        # Ley 9/2017 Contratos del Sector Publico
    "LRC": "BOE-A-2011-12628",         # Ley 20/2011 Registro Civil
    "LOPJM": "BOE-A-1996-1069",        # LO 1/1996 Proteccion Juridica del Menor
    "LJV": "BOE-A-2015-7391",          # Ley 15/2015 Jurisdiccion Voluntaria
    "LBRL": "BOE-A-1985-5392",         # Ley 7/1985 Bases de Regimen Local
    "TRLC": "BOE-A-2020-4859",         # RDLeg 1/2020 Ley Concursal
    "GDPR": "DOUE-L-2016-80807",       # RGPD (referencia UE; via otra ruta)
    "RGPD": "DOUE-L-2016-80807",
}

# Nombres largos -> sigla
NOMBRES = {
    "constitucion": "CE", "constitucion espanola": "CE",
    "codigo civil": "CC",
    "codigo de comercio": "CCOM", "codigo comercio": "CCOM",
    "codigo penal": "CP",
    "ley de enjuiciamiento civil": "LEC",
    "ley de enjuiciamiento criminal": "LECRIM",
    "estatuto de los trabajadores": "ET",
    "ley general tributaria": "LGT",
    "ley de arrendamientos urbanos": "LAU",
    "ley de propiedad horizontal": "LPH",
    "ley de sociedades de capital": "LSC",
    "ley hipotecaria": "LH",
}

_RE_BOE_ID = re.compile(r"^BOE-A-\d{4}-\d+$", re.IGNORECASE)
_RE_LEY_NUM = re.compile(r"(?:ley|lo|l\.o\.|real decreto|rd|rdl)\s*(\d+)\s*/\s*(\d{4})", re.IGNORECASE)


def _norm(t: str) -> str:
    d = unicodedata.normalize("NFKD", t)
    return "".join(c for c in d if not unicodedata.combining(c)).upper().strip()


def resolver_norma(ley: str, red: bool = True) -> str | None:
    """'LEC' / 'Codigo Civil' / 'BOE-A-2000-323' / 'Ley 29/1998' -> identificador BOE-A.

    Las siglas y nombres se resuelven sin red. Una cita por rango y numero
    ('Ley 29/1998', 'LO 3/2018', 'RDLeg 8/2015', 'RD 1065/2007') se resuelve con
    la API (filtro por numero oficial + rango + ambito estatal) si `red`.
    """
    l = ley.strip()
    if _RE_BOE_ID.match(l):
        return l.upper()
    n = _norm(l)
    if n in LEYES:
        return LEYES[n]
    # Nombres largos: comparar sin tildes ni mayusculas ('Código Civil' -> 'codigo civil').
    low = " ".join(_norm(l).lower().split())
    if low in NOMBRES:
        return LEYES[NOMBRES[low]]
    cita = parsear_rango_numero(l)
    if cita and red:
        return resolver_por_numero(*cita)
    return None


# Rango -> codigo de la API (verificados contra /legislacion-consolidada).
RANGOS = {
    "LO": ("1290", "Ley Organica"),
    "LEY": ("1300", "Ley"),
    "RDLEG": ("1310", "Real Decreto Legislativo"),
    "RDL": ("1320", "Real Decreto-ley"),
    "RD": ("1340", "Real Decreto"),
}

_RE_RANGO_NUM = re.compile(
    r"^\s*(?P<tipo>ley\s+org[aá]nica|l\.?\s*o\.?|real\s+decreto\s+legislativo|rd\s*leg\.?|"
    r"rdlegislativo|real\s+decreto[\s-]*ley|rd[\s-]*ley|rdl|real\s+decreto|r\.?\s*d\.?|ley)"
    r"\s*(?P<num>\d{1,4})\s*/\s*(?P<anio>\d{4})\b",
    re.IGNORECASE,
)


def parsear_rango_numero(texto: str) -> tuple[str, str] | None:
    """'Ley Orgánica 3/2018' -> ('LO', '3/2018'). Sin red."""
    m = _RE_RANGO_NUM.match(texto)
    if not m:
        return None
    t = re.sub(r"[\s.\-]", "", _norm(m.group("tipo")))
    if t in ("LEYORGANICA", "LO"):
        clave = "LO"
    elif t in ("REALDECRETOLEGISLATIVO", "RDLEG", "RDLEGISLATIVO"):
        clave = "RDLEG"
    elif t in ("REALDECRETOLEY", "RDLEY", "RDL"):
        clave = "RDL"
    elif t in ("REALDECRETO", "RD"):
        clave = "RD"
    else:
        clave = "LEY"
    return clave, f"{int(m.group('num'))}/{m.group('anio')}"


def consultar_api(query: str, limite: int = 20, desde: str = "", hasta: str = "",
                  orden_desc: bool = True) -> list[dict]:
    """Busqueda en servidor sobre legislacion consolidada (sintaxis query_string
    de la API oficial: `titulo:(a and b)`, `numero_oficial:"29/1998"`,
    `rango@codigo:1300`, `ambito@codigo:1`)."""
    import json

    q: dict = {"query": {"query_string": {"query": query}}}
    if orden_desc:
        q["sort"] = [{"fecha_disposicion": "desc"}]
    params: dict = {"query": json.dumps(q, ensure_ascii=False), "limit": limite}
    if desde:
        params["from"] = desde
    if hasta:
        params["to"] = hasta
    j = get_json(f"{API}/legislacion-consolidada", params=params)
    data = j.get("data", [])
    return data if isinstance(data, list) else []


def resolver_por_numero(rango: str, numero: str) -> str | None:
    """('LEY', '29/1998') -> 'BOE-A-1998-16718' (norma estatal)."""
    codigo = RANGOS.get(rango, RANGOS["LEY"])[0]
    try:
        res = consultar_api(f'numero_oficial:"{numero}" and rango@codigo:{codigo} '
                            f"and ambito@codigo:1", limite=5, orden_desc=False)
    except Exception:  # noqa: BLE001
        return None
    return res[0].get("identificador") if res else None


# ---------------------------------------------------------------------------
# Coincidencia de articulos: "394" / "art. 1902" / "439 bis"
# ---------------------------------------------------------------------------

def _clave_articulo(texto: str) -> str:
    """Normaliza el titulo de un articulo a su nucleo comparable.

    Distintas normas rotulan distinto segun su epoca:
      LEC (2000):  'Artículo 394. Condena en las costas...'  (id a394)
      CC  (1889):  'Art 1902'                                 (id art1902)
    Ambos deben reducirse a '1902' / '394'. Ademas 'Artículo 439 bis' -> '439 BIS'.
    Se recorta en el primer punto para descartar el epigrafe descriptivo.
    """
    t = _norm(texto)
    t = re.sub(r"\bARTICULOS?\b", " ", t)
    t = re.sub(r"\bART\b\.?", " ", t)
    t = t.split(".", 1)[0]           # quita el epigrafe tras el numero
    t = t.replace(".", " ")
    return " ".join(t.split())


# ---------------------------------------------------------------------------
# Disposiciones adicionales / transitorias / finales / derogatorias
# ---------------------------------------------------------------------------

_UNIDADES = ["", "PRIMERA", "SEGUNDA", "TERCERA", "CUARTA", "QUINTA", "SEXTA",
             "SEPTIMA", "OCTAVA", "NOVENA"]
_DECENAS = {2: "VIGESIMA", 3: "TRIGESIMA", 4: "CUADRAGESIMA", 5: "QUINCUAGESIMA",
            6: "SEXAGESIMA", 7: "SEPTUAGESIMA", 8: "OCTOGESIMA", 9: "NONAGESIMA"}
_TIPOS_DISP = {"A": "ADICIONAL", "T": "TRANSITORIA", "F": "FINAL", "D": "DEROGATORIA"}


def ordinal(n: int) -> str:
    """15 -> 'DECIMOQUINTA' (como rotula el BOE las disposiciones)."""
    if n < 10:
        return _UNIDADES[n]
    if n == 10:
        return "DECIMA"
    if n == 11:
        return "UNDECIMA"
    if n == 12:
        return "DUODECIMA"
    if n < 20:
        return {18: "DECIMOCTAVA"}.get(n, "DECIMO" + _UNIDADES[n - 10])
    d, u = divmod(n, 10)
    return _DECENAS[d] + (_UNIDADES[u] if u else "")


def _ordinal_comparable(t: str) -> str:
    """Iguala variantes: 'vigésima primera' / 'vigesimoprimera' / 'decimooctava'."""
    t = re.sub(r"[\s.]", "", t)
    t = re.sub(r"(VIGESIM|TRIGESIM|CUADRAGESIM|QUINCUAGESIM|SEXAGESIM|SEPTUAGESIM|"
               r"OCTOGESIM|NONAGESIM)O", r"\1A", t)
    return t.replace("DECIMOOCTAVA", "DECIMOCTAVA")


def clave_disposicion(texto: str) -> str | None:
    """'DA 15ª' / 'Disposición adicional decimoquinta. Depósito...' ->
    'ADICIONAL DECIMOQUINTA'. None si no es una disposicion."""
    t = _norm(texto)
    m = re.match(
        r"^\s*(?:DISPOSICION(?:ES)?|DISP\.?|D\.?)\s*"
        r"(ADICIONAL|TRANSITORIA|FINAL|DEROGATORIA|A|T|F|D)\b\.?\s*(.*)$", t)
    if not m:
        return None
    tipo = _TIPOS_DISP.get(m.group(1), m.group(1))
    resto = m.group(2).split(".", 1)[0].strip()
    num = re.match(r"^(\d{1,2})\s*[ªºAO]?$", resto)
    if num:
        ordn = ordinal(int(num.group(1)))
    else:
        ordn = resto
    return f"{tipo} {_ordinal_comparable(ordn)}".strip()


def buscar_articulo(ley: str, articulo: str) -> str:
    """Texto VIGENTE de un articulo de una ley espanola (legislacion consolidada)."""
    norma = resolver_norma(ley)
    if not norma:
        return (
            f"No reconozco la norma «{ley}». Prueba con una sigla conocida (LEC, CC, "
            f"CP, ET, LGT, LAU, LPH, LOPDGDD, LGSS...), el nombre completo, la cita "
            f"por rango y numero ('Ley 29/1998', 'LO 3/2018', 'RD 1065/2007') o el "
            f"identificador BOE-A (p.ej. BOE-A-2000-323). Si no conoces el numero, "
            f"buscar_boe('<materia>') lo localiza."
        )

    # 1) Indice de bloques (JSON) para localizar el articulo por su titulo.
    try:
        idx = get_json(f"{API}/legislacion-consolidada/id/{norma}/texto/indice")
    except Exception as e:  # noqa: BLE001
        return f"No pude leer el indice de {norma} en el BOE: {e}"

    bloques = idx.get("data", [{}])
    if isinstance(bloques, list) and bloques and isinstance(bloques[0], dict):
        bloques = bloques[0].get("bloque", [])
    disposicion = clave_disposicion(articulo)
    objetivo = _clave_articulo(articulo)

    bloque = None
    for b in bloques:
        tit = b.get("titulo") or ""
        if disposicion:
            if clave_disposicion(tit) == disposicion:
                bloque = b
                break
            continue
        if not re.match(r"\s*art", tit, re.IGNORECASE):   # 'Artículo...' o 'Art ...'
            continue
        if _clave_articulo(tit) == objetivo:
            bloque = b
            break
    if bloque is None:
        return (
            f"No encontre el artículo «{articulo}» en {ley} ({norma}). "
            f"Verifica el numero (la norma tiene {len(bloques)} bloques)."
        )

    # 2) Texto del bloque (XML).
    try:
        xml = get_xml(f"{API}/legislacion-consolidada/id/{norma}/texto/bloque/{bloque['id']}")
    except Exception as e:  # noqa: BLE001
        return f"Encontre el artículo pero no pude descargar su texto: {e}"

    return _formatear_bloque(xml, ley, norma, bloque)


def elegir_version(versiones: list, hoy: str | None = None):
    """De las <version> de un bloque, la VIGENTE hoy (la de mayor fecha_vigencia
    que no sea futura) y, si existe, la siguiente redaccion aun no vigente.

    El BOE devuelve todas las redacciones historicas en orden cronologico: la
    primera es la ORIGINAL. Quedarse con la primera da textos derogados (p.ej.
    art. 455 LEC con 'cinco dias' para apelar o el monitorio en pesetas).
    """
    import datetime as _dt

    hoy = hoy or _dt.date.today().strftime("%Y%m%d")
    con_fecha = [(v.get("fecha_vigencia") or "", i, v) for i, v in enumerate(versiones)]
    vigentes = [t for t in con_fecha if t[0] and t[0] <= hoy]
    futuras = sorted((t for t in con_fecha if t[0] > hoy), key=lambda t: (t[0], t[1]))
    if vigentes:
        actual = max(vigentes, key=lambda t: (t[0], t[1]))[2]
    elif con_fecha:
        actual = con_fecha[-1][2]
    else:
        actual = None
    return actual, (futuras[0][2] if futuras else None)


def _formatear_bloque(xml: str, ley: str, norma: str, bloque: dict) -> str:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return f"El BOE devolvio un XML no valido: {e}"

    version, futura = elegir_version(root.findall(".//version"))
    fecha_vig = version.get("fecha_vigencia") if version is not None else None
    id_norma_vig = version.get("id_norma") if version is not None else None

    # Texto del articulo y, aparte, las notas del BOE ('Se modifica por...',
    # 'Redaccion anterior: ...'), que sirven para atribuir reformas pero no son
    # parte del precepto.
    parrafos: list[str] = []
    notas: list[str] = []
    scope = version if version is not None else root
    for p in scope.iter("p"):
        txt = "".join(p.itertext()).strip()
        if not txt:
            continue
        (notas if (p.get("class") or "").startswith("nota") else parrafos).append(txt)
    cuerpo = "\n".join(parrafos) if parrafos else "(sin texto)"
    if notas:
        nt = "\n".join(notas)
        if len(nt) > 1500:
            nt = nt[:1500].rsplit("\n", 1)[0] + "\n[…mas notas en el enlace]"
        cuerpo += "\n\nNotas del BOE (reformas):\n" + nt

    def _fecha(f: str | None) -> str:
        if f and len(f) == 8:
            return f"{f[6:8]}/{f[4:6]}/{f[0:4]}"
        return f or "?"

    cab = f"【{ley} — {bloque.get('titulo')}】"
    if fecha_vig:
        cab += f" · vigente desde {_fecha(fecha_vig)}"
    pie = (
        f"\nFuente: BOE legislacion consolidada {norma}"
        + (f" · redaccion vigente dada por {id_norma_vig}" if id_norma_vig and id_norma_vig != norma else "")
        + f"\nhttps://www.boe.es/buscar/act.php?id={norma}"
    )
    if futura is not None:
        pie = (f"\nAVISO: hay una redaccion FUTURA de este articulo, vigente desde "
               f"{_fecha(futura.get('fecha_vigencia'))} (dada por {futura.get('id_norma')}). "
               f"Arriba va la vigente hoy." + pie)
    return f"{cab}\n\n{cuerpo}\n{pie}"


# ---------------------------------------------------------------------------
# Sumario del BOE de un dia
# ---------------------------------------------------------------------------

_SECCIONES = {
    "1": "I", "2": "II", "2A": "IIA", "2B": "IIB",
    "3": "III", "4": "IV", "5": "V", "5A": "VA", "5B": "VB",
}


def _fecha_api(fecha: str) -> str | None:
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


def _iter_items(node):
    """Recorre el arbol del sumario y va sacando los items (con identificador)."""
    if isinstance(node, list):
        for x in node:
            yield from _iter_items(x)
    elif isinstance(node, dict):
        if "identificador" in node and "titulo" in node:
            yield node
        else:
            for v in node.values():
                yield from _iter_items(v)


def sumario_boe(fecha: str, seccion: str = "", contiene: str = "") -> str:
    """Que se publico en el BOE de un dia. fecha: AAAA-MM-DD o DD/MM/AAAA."""
    f = _fecha_api(fecha)
    if not f:
        return f"Fecha no valida: «{fecha}». Usa AAAA-MM-DD o DD/MM/AAAA."
    try:
        d = get_json(f"{API}/boe/sumario/{f}")
    except Exception as e:  # noqa: BLE001
        return f"No pude leer el sumario del BOE de {fecha}: {e} (¿fue dia sin BOE?)"

    sumario = d.get("data", {}).get("sumario", {})
    filtro = _norm(contiene) if contiene else ""
    items = list(_iter_items(sumario.get("diario", sumario)))
    if filtro:
        items = [it for it in items if filtro in _norm(it.get("titulo", ""))]

    if not items:
        return f"Sin resultados en el BOE de {fecha}" + (f" con «{contiene}»" if contiene else "") + "."

    lineas = [f"BOE de {fecha}: {len(items)} entradas" + (f" con «{contiene}»" if contiene else "") + ":", ""]
    for it in items[:60]:
        lineas.append(f"• {it['identificador']} — {it['titulo'][:180]}")
    if len(items) > 60:
        lineas.append(f"... y {len(items) - 60} mas. Afina con 'contiene' o 'seccion'.")
    lineas.append("\nPara leer una entera: leer_boe con su identificador (BOE-A-...).")
    return "\n".join(lineas)


def _fecha_compacta(f: str) -> str | None:
    """AAAA-MM-DD / DD/MM/AAAA / AAAAMMDD -> AAAAMMDD."""
    return _fecha_api(f)


def buscar_boe(consulta: str, desde: str = "", hasta: str = "", limite: int = 15) -> str:
    """Localiza normas consolidadas cuyo TITULO contiene los terminos indicados.

    La API oficial de datos abiertos sirve el feed de legislacion consolidada
    ordenado por ultima actualizacion y filtrable por rango de fechas, pero NO
    ofrece busqueda textual en servidor. Por eso aqui se pagina el feed (acotado
    por fechas si se indican) y se filtra por titulo en cliente: es exhaustivo
    para lo reciente/modificado, y para una busqueda historica completa se ofrece
    el enlace del buscador oficial.
    """
    consulta = " ".join(consulta.split())
    if not consulta:
        return "Indica una materia o palabras del titulo de la norma."
    terminos = [_norm(t) for t in consulta.split() if t]

    params_fecha = ""
    d, h = _fecha_compacta(desde) if desde else None, _fecha_compacta(hasta) if hasta else None
    rango = {}
    if d:
        rango["from"] = d
    if h:
        rango["to"] = h

    # 1) Busqueda en servidor (toda la legislacion consolidada, no solo lo reciente).
    palabras = [re.sub(r"[^\w/]", "", t) for t in consulta.split()]
    palabras = [p for p in palabras if p]
    try:
        encontrados = consultar_api(
            "titulo:(" + " and ".join(palabras) + ")", limite=limite,
            desde=d or "", hasta=h or "",
        ) if palabras else []
    except Exception:  # noqa: BLE001
        encontrados = []
    if encontrados:
        return _listar_normas(encontrados, consulta, "busqueda en la API oficial, mas recientes primero")

    # 2) Respaldo: paginar el feed y filtrar por titulo en cliente.
    encontrados = []
    PAG = 50
    MAX_PAGINAS = 12  # hasta 600 normas del feed
    for pagina in range(MAX_PAGINAS):
        params = dict(rango, limit=PAG, offset=pagina * PAG)
        try:
            j = get_json(f"{API}/legislacion-consolidada", params=params)
        except Exception as e:  # noqa: BLE001
            if not encontrados:
                return f"No pude consultar el feed de legislacion del BOE: {e}"
            break
        lote = j.get("data", [])
        if not lote:
            break
        for n in lote:
            titulo = n.get("titulo", "")
            tnorm = _norm(titulo)
            if all(t in tnorm for t in terminos):
                encontrados.append(n)
                if len(encontrados) >= limite:
                    break
        if len(encontrados) >= limite:
            break

    url_oficial = (
        "https://www.boe.es/buscar/legislacion.php?campo%5B0%5D=TIT&dato%5B0%5D="
        + consulta.replace(" ", "+")
    )
    if not encontrados:
        return (
            f"Sin coincidencias por titulo para «{consulta}» en el feed de "
            f"legislacion consolidada (lo reciente/modificado). Para una busqueda "
            f"historica completa usa el buscador oficial:\n{url_oficial}"
        )

    return _listar_normas(encontrados, consulta, "feed de legislacion consolidada, mas recientes primero")


def _listar_normas(encontrados: list[dict], consulta: str, origen: str) -> str:
    url_oficial = (
        "https://www.boe.es/buscar/legislacion.php?campo%5B0%5D=TIT&dato%5B0%5D="
        + consulta.replace(" ", "+")
    )
    lineas = [
        f"{len(encontrados)} norma(s) cuyo titulo contiene «{consulta}» ({origen}):",
        "",
    ]
    for n in encontrados:
        rango_txt = (n.get("rango") or {}).get("texto", "")
        fdisp = n.get("fecha_disposicion", "")
        if len(fdisp) == 8:
            fdisp = f"{fdisp[6:8]}/{fdisp[4:6]}/{fdisp[0:4]}"
        lineas.append(f"• {n.get('identificador','')} — {rango_txt} · {fdisp}")
        lineas.append(f"    {n.get('titulo','')[:170]}")
    lineas.append(
        f"\nLeer el articulado: buscar_articulo(<sigla o BOE-A>, <articulo>).\n"
        f"Busqueda historica completa (oficial): {url_oficial}"
    )
    return "\n".join(lineas)


def novedades_boe(contiene: str, desde: str, hasta: str, seccion: str = "") -> str:
    """Barre los sumarios del BOE entre dos fechas (max 31 dias) y devuelve los
    items cuyo TITULO contiene el texto/NIF indicado. Vigilancia del BOE bajo
    demanda: notificaciones a un cliente, publicaciones sobre una empresa, etc.
    """
    import datetime as _dt

    if not contiene.strip():
        return "Indica el texto o NIF a vigilar en los titulos del BOE."
    d, h = _fecha_api(desde), _fecha_api(hasta)
    if not d or not h:
        return "Fechas no validas. Usa AAAA-MM-DD (obligatorias desde y hasta)."
    d0 = _dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    h0 = _dt.date(int(h[:4]), int(h[4:6]), int(h[6:8]))
    if h0 < d0:
        d0, h0 = h0, d0
    if (h0 - d0).days > 31:
        return "El rango no puede superar 31 dias."

    filtro = _norm(contiene)
    hits: list[str] = []
    dia = d0
    dias_con_boe = 0
    while dia <= h0:
        f = dia.strftime("%Y%m%d")
        try:
            j = get_json(f"{API}/boe/sumario/{f}")
            dias_con_boe += 1
            sumario = j.get("data", {}).get("sumario", {})
            for it in _iter_items(sumario.get("diario", sumario)):
                if filtro in _norm(it.get("titulo", "")):
                    hits.append(f"• {dia.strftime('%d/%m/%Y')} · {it['identificador']} — {it['titulo'][:160]}")
        except Exception:  # noqa: BLE001 (dia sin BOE, festivo...) -> se salta
            pass
        dia += _dt.timedelta(days=1)

    if not hits:
        return (
            f"Sin coincidencias de «{contiene}» en los titulos del BOE entre "
            f"{desde} y {hasta} ({dias_con_boe} dias con BOE revisados)."
        )
    cab = f"{len(hits)} coincidencia(s) de «{contiene}» en el BOE ({desde} a {hasta}):"
    return cab + "\n\n" + "\n".join(hits[:80]) + (
        f"\n... y {len(hits)-80} mas." if len(hits) > 80 else ""
    ) + "\n\nLeer una: leer_boe con su identificador."


def leer_boe(identificador: str) -> str:
    """Texto de una disposicion del BOE consolidada por su BOE-A id."""
    ident = identificador.strip().upper()
    if not _RE_BOE_ID.match(ident):
        return (
            f"Identificador no valido: «{identificador}». Debe ser BOE-A-AAAA-N. "
            f"(Para el texto vigente de un articulo usa mejor buscar_articulo.)"
        )
    try:
        idx = get_json(f"{API}/legislacion-consolidada/id/{ident}/texto/indice")
    except Exception as e:  # noqa: BLE001
        return (
            f"No pude abrir {ident} como norma consolidada ({e}). Enlace oficial: "
            f"https://www.boe.es/buscar/doc.php?id={ident}"
        )
    bloques = idx.get("data", [{}])
    if isinstance(bloques, list) and bloques and isinstance(bloques[0], dict):
        bloques = bloques[0].get("bloque", [])
    titulos = [b.get("titulo", "") for b in bloques if b.get("titulo")]
    return (
        f"Norma consolidada {ident} — {len(titulos)} bloques.\n"
        f"Primeros: " + "; ".join(titulos[:12]) + "\n"
        f"Para un articulo concreto: buscar_articulo('{ident}', 'N').\n"
        f"Texto completo oficial: https://www.boe.es/buscar/act.php?id={ident}"
    )
