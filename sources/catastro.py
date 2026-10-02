"""Catastro — datos catastrales NO protegidos, via los servicios OVC oficiales.

Direccion General del Catastro (Ministerio de Hacienda). Servicios abiertos,
sin captcha ni login, pensados para consulta automatizada de datos catastrales
NO protegidos: superficie, uso, año de construccion, plantas, localizacion y
referencia catastral. NUNCA devuelven titular ni valor catastral (datos
protegidos): este modulo no los pide ni los expone.

Endpoints (host https://ovc.catastro.meh.es):

  Callejero y consulta de datos (WCF REST JSON):
    /OVCServWeb/OVCWcfCallejero/COVCCallejero.svc/json/<Metodo>
      ObtenerProvincias                          -> provincias del Catastro comun
      ObtenerMunicipios(Provincia, Municipio)    -> municipios
      ObtenerCallejero(Provincia, Municipio, TipoVia, NombreVia) -> vias (sin filtro
                                                    de servidor: se filtra en cliente)
      Consulta_DNPRC(RefCat)                      -> inmueble por referencia catastral
      Consulta_DNPLOC(Provincia, Municipio, Sigla, Calle, Numero) -> por direccion
      Consulta_DNPPP(Provincia, Municipio, Poligono, Parcela)     -> rustica pol/parc

  Coordenadas (ASMX SOAP, admite GET -> XML):
    /OVCServWeb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/<Metodo>
      Consulta_RCCOOR(SRS, Coordenada_X, Coordenada_Y) -> referencia por coordenadas

Pais Vasco (Araba, Bizkaia, Gipuzkoa) y Navarra tienen catastro FORAL propio y no
estan en estos servicios: el modulo lo detecta y avisa.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET

from common.http import get_json, get_xml

HOST = "https://ovc.catastro.meh.es"
CALLEJERO = f"{HOST}/OVCServWeb/OVCWcfCallejero/COVCCallejero.svc/json"
COORDENADAS = f"{HOST}/OVCServWeb/OVCSWLocalizacionRC/OVCCoordenadas.asmx"

# Provincias de catastro foral (no cubiertas por el Catastro comun del Estado).
# Codigo INE de provincia y nombres/variantes (sin tildes, en mayusculas).
FORAL_CP = {"01", "20", "48", "31"}
FORAL_NOMBRES = {
    "ALAVA", "ARABA", "ARABA/ALAVA", "ARABA ALAVA",
    "GUIPUZCOA", "GIPUZKOA",
    "VIZCAYA", "BIZKAIA",
    "NAVARRA", "NAFARROA", "NAVARRA/NAFARROA",
}

_RE_RC14 = re.compile(r"^[0-9A-Z]{14}$")
_RE_RC20 = re.compile(r"^[0-9A-Z]{20}$")


def _norm(t: str) -> str:
    """Mayusculas sin tildes (pero conservando la Ñ) y sin espacios sobrantes.

    El Catastro almacena los nombres en mayusculas y CON Ñ (p.ej. «A CORUÑA»,
    «VALDEPEÑAS»), asi que la eñe se preserva; solo se retiran los acentos.
    """
    prot = (t or "").replace("ñ", "\0n").replace("Ñ", "\0N")
    d = unicodedata.normalize("NFKD", prot)
    s = "".join(ch for ch in d if not unicodedata.combining(ch))
    s = s.replace("\0n", "Ñ").replace("\0N", "Ñ")
    return " ".join(s.upper().split())


def _es_foral(provincia: str = "", cp: str = "") -> bool:
    if cp and cp.zfill(2) in FORAL_CP:
        return True
    return _norm(provincia) in FORAL_NOMBRES


def _limpiar_rc(rc: str) -> str:
    """Normaliza una referencia catastral: sin espacios, en mayusculas."""
    return re.sub(r"\s+", "", rc or "").upper()


def _fmt_sup(v: str | None) -> str:
    """La superficie llega como cadena de metros (a veces con punto de millar)."""
    if not v:
        return "?"
    return f"{v.replace('.', '')} m2"


# ---------------------------------------------------------------------------
# Callejero: provincias / municipios / vias
# ---------------------------------------------------------------------------

def callejero_catastro(municipio: str = "", provincia: str = "",
                       via: str = "", numero: str = "") -> str:
    """Desambigua direcciones: lista provincias, municipios o vias del Catastro.

    Uso escalonado:
      - sin argumentos                -> lista de provincias.
      - solo `provincia`              -> municipios de esa provincia.
      - `municipio` (+ provincia)     -> confirma el municipio.
      - `municipio` + `via`           -> vias que contienen ese texto.
    Devuelve texto legible. Para localizar un inmueble concreto usa
    consultar_catastro.
    """
    prov = provincia.strip()
    mun = municipio.strip()
    v = via.strip()

    if _es_foral(prov):
        return _aviso_foral(prov)

    # 1) Sin provincia ni municipio -> provincias.
    if not prov and not mun:
        return _listar_provincias()

    # 2) Provincia dada pero sin municipio -> municipios de la provincia.
    if prov and not mun:
        return _listar_municipios(prov, "")

    # 3) Hay municipio: si no piden via, confirmar/listar municipios homonimos.
    if not v:
        return _listar_municipios(prov, mun)

    # 4) Municipio + via -> vias que contienen el texto.
    return _listar_vias(prov, mun, v)


def _listar_provincias() -> str:
    try:
        d = get_json(f"{CALLEJERO}/ObtenerProvincias")
    except Exception as e:  # noqa: BLE001
        return f"No pude obtener las provincias del Catastro: {e}"
    provs = (d.get("consulta_provincieroResult", {})
             .get("provinciero", {}).get("prov", []))
    nombres = [p.get("np", "") for p in provs if p.get("np")]
    return (
        f"Provincias del Catastro comun ({len(nombres)}):\n"
        + ", ".join(nombres)
        + "\n\nNota: Pais Vasco (Araba, Bizkaia, Gipuzkoa) y Navarra tienen "
        "catastro foral propio y no figuran aqui."
    )


def _listar_municipios(provincia: str, municipio: str) -> str:
    try:
        d = get_json(f"{CALLEJERO}/ObtenerMunicipios",
                     params={"Provincia": provincia, "Municipio": municipio})
    except Exception as e:  # noqa: BLE001
        return f"No pude obtener municipios de «{provincia}»: {e}"
    res = d.get("consulta_municipieroResult", {})
    err = _errores(res)
    if err:
        return f"Catastro: {err} (provincia «{provincia}»)."
    munis = res.get("municipiero", {}).get("muni", [])
    nombres = [m.get("nm", "") for m in munis if m.get("nm")]
    if not nombres:
        return f"Sin municipios para «{municipio or provincia}»."
    cab = (f"Municipios en {provincia}" if not municipio
           else f"Municipios que coinciden con «{municipio}» en {provincia}")
    return f"{cab} ({len(nombres)}):\n" + ", ".join(nombres)


def _listar_vias(provincia: str, municipio: str, via: str) -> str:
    try:
        d = get_json(f"{CALLEJERO}/ObtenerCallejero",
                     params={"Provincia": provincia, "Municipio": municipio,
                             "TipoVia": "", "NombreVia": ""})
    except Exception as e:  # noqa: BLE001
        return f"No pude obtener el callejero de «{municipio}»: {e}"
    res = d.get("consulta_callejeroResult", {})
    err = _errores(res)
    if err:
        return f"Catastro: {err} (municipio «{municipio}», provincia «{provincia}»)."
    calles = res.get("callejero", {}).get("calle", [])
    filtro = _norm(via)
    hits = []
    for c in calles:
        dr = c.get("dir", {})
        nv, tv = dr.get("nv", ""), dr.get("tv", "")
        if filtro in _norm(nv):
            hits.append(f"{tv} {nv}".strip())
    hits = sorted(set(hits))
    if not hits:
        return (f"No encontre vias con «{via}» en {municipio} ({provincia}). "
                f"El municipio tiene {len(calles)} vias en total.")
    cab = f"Vias con «{via}» en {municipio} ({provincia}): {len(hits)}"
    cuerpo = "\n".join(f"- {h}" for h in hits[:60])
    if len(hits) > 60:
        cuerpo += f"\n... y {len(hits) - 60} mas. Afina el texto de la via."
    return f"{cab}\n{cuerpo}"


# ---------------------------------------------------------------------------
# Consulta de un inmueble (datos no protegidos)
# ---------------------------------------------------------------------------

def consultar_catastro(referencia_catastral: str = "", direccion: str = "",
                       municipio: str = "", provincia: str = "",
                       poligono: str = "", parcela: str = "",
                       coordenadas: str = "", sigla: str = "",
                       numero: str = "") -> str:
    """Identifica un inmueble y devuelve sus datos catastrales NO protegidos.

    Vias de busqueda (en orden de prioridad):
      - `referencia_catastral`: 14 o 20 caracteres.
      - `coordenadas`: 'lat,lon' en WGS84 (EPSG:4326).
      - `poligono` + `parcela` (+ municipio + provincia): finca rustica.
      - `direccion` (+ municipio + provincia): urbana por calle/numero. Admite
        `sigla` (tipo de via, p.ej. CL) y `numero` sueltos, o el numero dentro
        de `direccion`.

    Devuelve superficie, uso, año, plantas, localizacion y referencia. NO
    devuelve titular ni valor catastral (datos protegidos). Pais Vasco y Navarra
    (catastro foral) no estan cubiertos: se avisa.
    """
    if _es_foral(provincia):
        return _aviso_foral(provincia)

    if referencia_catastral.strip():
        return _por_referencia(_limpiar_rc(referencia_catastral))
    if coordenadas.strip():
        return _por_coordenadas(coordenadas.strip())
    if poligono.strip() and parcela.strip():
        return _por_poligono_parcela(provincia, municipio, poligono.strip(),
                                     parcela.strip())
    if direccion.strip() or numero.strip():
        return _por_direccion(provincia, municipio, direccion, sigla, numero)

    return (
        "Indica al menos una via de busqueda: referencia_catastral (14 o 20 car.), "
        "coordenadas 'lat,lon', poligono+parcela (rustica) o direccion+municipio."
    )


def _por_referencia(rc: str) -> str:
    if not (_RE_RC14.match(rc) or _RE_RC20.match(rc)):
        return (f"Referencia catastral no valida: «{rc}». Debe tener 14 o 20 "
                f"caracteres alfanumericos.")
    try:
        d = get_json(f"{CALLEJERO}/Consulta_DNPRC", params={"RefCat": rc})
    except Exception as e:  # noqa: BLE001
        return f"No pude consultar la referencia {rc}: {e}"
    res = d.get("consulta_dnprcResult", {})
    err = _errores(res)
    if err:
        extra = ("\n(Si el inmueble esta en Pais Vasco o Navarra, su catastro es "
                 "foral y no figura en este servicio.)") if _err_sin_datos(res) else ""
        return f"Catastro (RC {rc}): {err}.{extra}"
    return _formatear_resultado(res, origen=f"referencia catastral {rc}")


def _por_direccion(provincia: str, municipio: str, direccion: str,
                   sigla: str, numero: str) -> str:
    if not municipio.strip():
        return "Para buscar por direccion necesito tambien el municipio."
    sig, calle, num = _partir_direccion(direccion, sigla, numero)
    if not calle:
        return "No entendi la via. Ejemplo: direccion='Calle Alcala 1'."
    try:
        d = get_json(f"{CALLEJERO}/Consulta_DNPLOC",
                     params={"Provincia": provincia, "Municipio": municipio,
                             "Sigla": sig, "Calle": calle, "Numero": num})
    except Exception as e:  # noqa: BLE001
        return f"No pude consultar la direccion: {e}"
    res = d.get("consulta_dnplocResult", {})

    # Cuando el numero exacto no existe, el servicio sugiere numeros cercanos.
    numerero = res.get("numerero", {}).get("nump")
    if numerero:
        nums = sorted({n.get("num", {}).get("pnp", "") for n in numerero if n.get("num")},
                      key=lambda x: (len(x), x))
        return (f"No hay portal «{num}» en {calle} ({municipio}). "
                f"Numeros proximos con inmueble: {', '.join(n for n in nums if n)}. "
                f"Reintenta con uno de ellos.")

    err = _errores(res)
    if err:
        return f"Catastro (direccion {calle} {num}, {municipio}): {err}."
    return _formatear_resultado(res, origen=f"{calle} {num}, {municipio}")


def _por_poligono_parcela(provincia: str, municipio: str,
                          poligono: str, parcela: str) -> str:
    if not (provincia.strip() and municipio.strip()):
        return ("Para rustica (poligono/parcela) necesito provincia y municipio, "
                "ademas del poligono y la parcela.")
    try:
        d = get_json(f"{CALLEJERO}/Consulta_DNPPP",
                     params={"Provincia": provincia, "Municipio": municipio,
                             "Poligono": poligono, "Parcela": parcela})
    except Exception as e:  # noqa: BLE001
        return f"No pude consultar poligono {poligono} parcela {parcela}: {e}"
    res = d.get("consulta_dnpppResult", {})
    err = _errores(res)
    if err:
        return (f"Catastro (pol {poligono} parc {parcela}, {municipio} "
                f"[{provincia}]): {err}.")
    return _formatear_resultado(
        res, origen=f"poligono {poligono} parcela {parcela}, {municipio}")


def _por_coordenadas(coords: str) -> str:
    m = re.match(r"^\s*(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)\s*$", coords)
    if not m:
        return "Coordenadas no validas. Formato: 'lat,lon' (p.ej. '40.4172,-3.7022')."
    lat = m.group(1).replace(",", ".")
    lon = m.group(2).replace(",", ".")
    try:
        xml = get_xml(f"{COORDENADAS}/Consulta_RCCOOR",
                      params={"SRS": "EPSG:4326",
                              "Coordenada_X": lon, "Coordenada_Y": lat})
    except Exception as e:  # noqa: BLE001
        return f"No pude consultar por coordenadas: {e}"

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return f"El Catastro devolvio un XML no valido: {e}"

    err = _xml_error(root)
    if err:
        cod, des = err
        extra = ""
        if cod == "16":  # sin referencia para esas coordenadas
            extra = (" El punto puede caer en viario/zona sin parcela, o en Pais "
                     "Vasco/Navarra (catastro foral, no cubierto).")
        return f"Catastro (coordenadas {lat},{lon}): {des}.{extra}"

    coord = _xml_find(root, "coord")
    if coord is None:
        return f"Sin referencia catastral para las coordenadas {lat},{lon}."
    pc1 = _xml_text(coord, "pc1")
    pc2 = _xml_text(coord, "pc2")
    ldt = _xml_text(coord, "ldt")
    rc = f"{pc1}{pc2}"
    salida = [
        f"Referencia catastral en {lat},{lon}: {rc}",
        f"Localizacion: {ldt}" if ldt else "",
        "",
        f"Para el detalle del inmueble: consultar_catastro(referencia_catastral='{rc}').",
    ]
    return "\n".join(s for s in salida if s != "")


# ---------------------------------------------------------------------------
# Formateo del resultado (comun a DNPRC / DNPLOC / DNPPP)
# ---------------------------------------------------------------------------

def _formatear_resultado(res: dict, origen: str) -> str:
    """Convierte la respuesta (bico unico o lista de inmuebles) en texto."""
    bico = res.get("bico")
    if bico:
        bis = [bico.get("bi", {})]
        finca = bico.get("finca", {})
        lcons = bico.get("bico_lcons") or bico.get("lcons")
    else:
        # DNPLOC: lista de inmuebles bajo lrcdnp.rcdnp
        rcdnp = res.get("lrcdnp", {}).get("rcdnp", [])
        bis = rcdnp if isinstance(rcdnp, list) else [rcdnp]
        finca, lcons = {}, None

    if not bis:
        return f"Sin datos catastrales para {origen}."

    if len(bis) > 1:
        lineas = [f"Se encontraron {len(bis)} inmuebles en {origen}:", ""]
        for bi in bis:
            lineas.append(_linea_inmueble(bi))
        lineas.append("\nPara el detalle de uno: consultar_catastro con su "
                      "referencia_catastral (20 car.).")
        return "\n".join(lineas)

    return _detalle_inmueble(bis[0], finca, lcons, origen)


def _rc_completa(bi: dict) -> str:
    rc = bi.get("idbi", {}).get("rc") or bi.get("rc") or {}
    return (f"{rc.get('pc1','')}{rc.get('pc2','')}{rc.get('car','')}"
            f"{rc.get('cc1','')}{rc.get('cc2','')}")


def _localizacion(bi: dict) -> str:
    if bi.get("ldt"):
        return bi["ldt"]
    # DNPLOC no trae ldt: reconstruir desde dt.locs.lous.lourb.dir
    dr = (bi.get("dt", {}).get("locs", {}).get("lous", {})
          .get("lourb", {}).get("dir", {}))
    if dr:
        partes = [dr.get("tv", ""), dr.get("nv", ""), dr.get("pnp", "")]
        base = " ".join(p for p in partes if p)
        nm = bi.get("dt", {}).get("nm", "")
        return f"{base} ({nm})".strip()
    return ""


def _linea_inmueble(bi: dict) -> str:
    debi = bi.get("debi", {})
    rc = _rc_completa(bi)
    uso = debi.get("luso", "?")
    sup = _fmt_sup(debi.get("sfc"))
    loc = _localizacion(bi)
    return f"- {rc} | {uso} | {sup} | {loc}"


def _detalle_inmueble(bi: dict, finca: dict, lcons, origen: str) -> str:
    idbi = bi.get("idbi", {})
    cn = idbi.get("cn", "")  # UR urbana / RU rustica
    naturaleza = {"UR": "Urbana", "RU": "Rustica"}.get(cn, cn or "?")
    debi = bi.get("debi", {})
    rc = _rc_completa(bi)
    loc = _localizacion(bi)

    lineas = [
        f"Inmueble {rc}",
        f"  Naturaleza: {naturaleza}",
        f"  Localizacion: {loc}" if loc else "",
        f"  Uso principal: {debi.get('luso', '?')}",
        f"  Superficie construida: {_fmt_sup(debi.get('sfc'))}",
        f"  Año de construccion: {debi.get('ant', '?')}",
    ]

    # Rustica: poligono/parcela/paraje.
    lorus = (bi.get("dt", {}).get("locs", {}).get("lors", {}).get("lorus", {}))
    if lorus:
        cpp = lorus.get("cpp", {})
        lineas.append(f"  Poligono/Parcela: {cpp.get('cpo','?')}/{cpp.get('cpa','?')}")
        if lorus.get("npa"):
            lineas.append(f"  Paraje: {lorus.get('npa')}")

    # Datos de la finca (superficie de suelo, tipo, enlace grafico).
    if finca:
        if finca.get("ltp"):
            lineas.append(f"  Finca: {finca.get('ltp')}")
        ss = finca.get("dff", {}).get("ss")
        if ss:
            lineas.append(f"  Superficie de suelo (finca): {_fmt_sup(ss)}")
        igraf = finca.get("infgraf", {}).get("igraf")
        if igraf:
            lineas.append(f"  Cartografia: {igraf}")

    # Construcciones / plantas.
    if lcons:
        cons = lcons if isinstance(lcons, list) else [lcons]
        if cons:
            lineas.append(f"  Construcciones ({len(cons)}):")
            for c in cons[:12]:
                uso = c.get("lcd", "?")
                loint = c.get("dt", {}).get("lourb", {}).get("loint", {})
                planta = loint.get("pt", "")
                puerta = loint.get("pu", "")
                sup = _fmt_sup(c.get("dfcons", {}).get("stl"))
                detalle = uso
                if planta:
                    detalle += f", planta {planta}"
                if puerta:
                    detalle += f", pta {puerta}"
                lineas.append(f"    - {detalle} | {sup}")
            if len(cons) > 12:
                lineas.append(f"    ... y {len(cons) - 12} construcciones mas.")

    lineas.append("")
    lineas.append(f"Fuente: Direccion General del Catastro (datos no protegidos). "
                  f"Consulta por {origen}.")
    lineas.append("Este servicio NO facilita titular ni valor catastral (datos "
                  "protegidos).")
    return "\n".join(s for s in lineas if s != "")


# ---------------------------------------------------------------------------
# Utilidades de errores (JSON y XML)
# ---------------------------------------------------------------------------

def _errores(res: dict) -> str:
    """Extrae el mensaje de error del bloque 'control'/'lerr', si lo hay."""
    control = res.get("control", {})
    if not control.get("cuerr"):
        return ""
    lerr = res.get("lerr")
    errs = []
    if isinstance(lerr, dict):
        lerr = lerr.get("err", [])
    if isinstance(lerr, dict):
        lerr = [lerr]
    for e in (lerr or []):
        des = (e.get("des") or "").strip()
        if des:
            errs.append(des)
    return "; ".join(errs) if errs else "consulta sin resultados"


def _err_sin_datos(res: dict) -> bool:
    lerr = res.get("lerr")
    if isinstance(lerr, dict):
        lerr = lerr.get("err", [lerr])
    for e in (lerr or []):
        if str(e.get("cod")) in {"5", "16", "17"}:
            return True
    return False


_NS = re.compile(r"\{.*\}")


def _tag(el) -> str:
    return _NS.sub("", el.tag)


def _xml_find(root, name):
    for el in root.iter():
        if _tag(el) == name:
            return el
    return None


def _xml_text(parent, name) -> str:
    el = _xml_find(parent, name)
    return (el.text or "").strip() if el is not None else ""


def _xml_error(root):
    """Devuelve (cod, des) del primer <err> del XML de coordenadas, o None."""
    err = _xml_find(root, "err")
    if err is None:
        return None
    return _xml_text(err, "cod"), _xml_text(err, "des")


def _aviso_foral(provincia: str) -> str:
    return (
        f"«{provincia}» pertenece al catastro FORAL (Pais Vasco o Navarra), que "
        f"gestiona su propia Diputacion/Hacienda y NO figura en los servicios de la "
        f"Direccion General del Catastro. Consultalo en la sede foral correspondiente "
        f"(Araba, Bizkaia, Gipuzkoa o Navarra)."
    )


# ---------------------------------------------------------------------------
# Auxiliar: partir una direccion en sigla (tipo de via) + via + numero
# ---------------------------------------------------------------------------

# Prefijo de via (normalizado) -> sigla oficial del Catastro (tv).
_SIGLAS = {
    "CALLE": "CL", "C/": "CL", "CL": "CL",
    "AVENIDA": "AV", "AVDA": "AV", "AVD": "AV", "AV": "AV",
    "PLAZA": "PZ", "PZA": "PZ", "PL": "PZ", "PZ": "PZ",
    "PASEO": "PS", "PSO": "PS", "PO": "PS", "PS": "PS",
    "CAMINO": "CM", "CMNO": "CM", "CM": "CM",
    "CARRETERA": "CR", "CTRA": "CR", "CR": "CR",
    "TRAVESIA": "TR", "TRVA": "TR", "TR": "TR",
    "RONDA": "RD", "RD": "RD",
    "GLORIETA": "GL", "GL": "GL",
    "URBANIZACION": "UR", "URB": "UR", "UR": "UR",
    "POLIGONO": "PG", "PG": "PG",
}


def _partir_direccion(direccion: str, sigla: str, numero: str):
    """De 'Calle Alcala 1' saca ('CL', 'ALCALA', '1').

    Respeta `sigla` y `numero` si se pasan sueltos; en su defecto los deduce del
    texto. La via se devuelve en mayusculas (como la almacena el Catastro).
    """
    texto = (direccion or "").strip()
    num = (numero or "").strip()
    sig = (sigla or "").strip().upper()
    sig = _SIGLAS.get(sig, sig)  # normaliza 'CALLE'->'CL' si vino en `sigla`

    # Si no dieron numero suelto, tomar el ultimo numero de la direccion.
    if not num and texto:
        m = re.search(r"(\d+)\s*$", texto)
        if m:
            num = m.group(1)
            texto = texto[:m.start()].strip()

    # Deducir la sigla del prefijo de la cadena y retirarla del nombre de via.
    if texto:
        m = re.match(r"^\s*([A-Za-zÁÉÍÓÚÑáéíóúñ/]+\.?)\s+(.*)$", texto)
        if m:
            pref = _norm(m.group(1).rstrip("."))
            if pref in _SIGLAS:
                if not sig:
                    sig = _SIGLAS[pref]
                texto = m.group(2).strip()

    return sig, _norm(texto), num
