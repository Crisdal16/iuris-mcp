"""Tablas de codigos oficiales del CENDOJ.

Los codigos de organo NO son inventados: se obtuvieron de las facetas del propio
buscador del CENDOJ (campo "organos"). Son los que espera el backend en el
formulario de busqueda.

Ojo con la forma de los codigos: la mayoria son de 2 digitos (11..85), pero
algunos valores de faceta son codigos JERARQUICOS mas largos que concatenan
organo + seccion (p.ej. 2264 = Sala de Apelacion de la AN, sobre el organo 22;
31201202 = Seccion de Apelacion Penal, sobre el organo 31). Por eso los codigos
se manejan SIEMPRE como str opaco, nunca como int.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Codigos de organo (38 valores, tal y como los publica la faceta del CENDOJ)
# ---------------------------------------------------------------------------

ORGANOS: dict[str, str] = {
    # Tribunal Supremo
    "11": "TRIBUNAL SUPREMO. SALA DE LO CIVIL",
    "12": "TRIBUNAL SUPREMO. SALA DE LO PENAL",
    "13": "TRIBUNAL SUPREMO. SALA DE LO CONTENCIOSO",
    "14": "TRIBUNAL SUPREMO. SALA DE LO SOCIAL",
    "15": "TRIBUNAL SUPREMO. SALA DE LO MILITAR",
    "16": "TRIBUNAL SUPREMO. SALA DE LO ESPECIAL",
    # Audiencia Nacional
    "22": "AUDIENCIA NACIONAL. SALA DE LO PENAL",
    "2264": "SALA DE APELACION DE LA AUDIENCIA NACIONAL",
    "23": "AUDIENCIA NACIONAL. SALA DE LO CONTENCIOSO",
    "24": "AUDIENCIA NACIONAL. SALA DE LO SOCIAL",
    "25": "AUDIENCIA NACIONAL. JUZGADO CENTRAL DE VIGILANCIA PENITENCIARIA",
    "26": "AUDIENCIA NACIONAL. JUZGADO CENTRAL DE MENORES",
    "27": "AUDIENCIA NACIONAL. JUZGADOS CENTRALES DE INSTRUCCION",
    "28": "AUDIENCIA NACIONAL. JUZGADOS CENTRALES DE LO PENAL",
    "29": "AUDIENCIA NACIONAL. JUZGADOS CENTRALES DE LO CONTENCIOSO",
    # Tribunales Superiores de Justicia
    "31": "TRIBUNAL SUPERIOR DE JUSTICIA. SALA DE LO CIVIL Y PENAL",
    "31201202": "SECCION DE APELACION PENAL. TSJ SALA DE LO CIVIL Y PENAL",
    "33": "TRIBUNAL SUPERIOR DE JUSTICIA. SALA DE LO CONTENCIOSO",
    "34": "TRIBUNAL SUPERIOR DE JUSTICIA. SALA DE LO SOCIAL",
    # Audiencias
    "36": "AUDIENCIA TERRITORIAL",
    "37": "AUDIENCIA PROVINCIAL",
    "38": "AUDIENCIA PROVINCIAL. TRIBUNAL JURADO",
    # Juzgados / Tribunales de Instancia
    "41": "JUZGADO DE 1a INST. INSTR. / TRIBUNAL INSTANCIA SEC. CIVIL INSTR.",
    "42": "JUZGADO DE PRIMERA INSTANCIA / TRIBUNAL INSTANCIA SEC. CIVIL",
    "43": "JUZGADO DE INSTRUCCION",
    "44": "JUZGADO DE LO SOCIAL / TRIBUNAL INSTANCIA SEC. SOCIAL",
    "45": "JUZGADO DE LO CONTENCIOSO ADMINISTRATIVO",
    "47": "JUZGADO DE LO MERCANTIL / TRIBUNAL INSTANCIA SEC. MERCANTIL",
    "48": "JUZGADO DE VIOLENCIA SOBRE LA MUJER",
    "50": "TRIBUNAL INSTANCIA SEC. FAMILIA, INFANCIA Y CAPACIDAD",
    "51": "JUZGADO DE LO PENAL / TRIBUNAL INSTANCIA SEC. PENAL",
    "52": "JUZGADO DE VIGILANCIA PENITENCIARIA",
    "53": "JUZGADO DE MENORES / TRIBUNAL INSTANCIA SEC. MENORES",
    # Jurisdiccion militar
    "75": "CONSEJO SUPREMO DE JUSTICIA MILITAR",
    "83": "TRIBUNAL MILITAR TERRITORIAL",
    "85": "TRIBUNAL MILITAR CENTRAL",
    # Marca de la Union Europea
    "1001": "TRIBUNAL DE MARCA DE LA UE",
    "1002": "JUZGADOS DE MARCA DE LA UE",
}

# ---------------------------------------------------------------------------
# Alias comodos -> codigos. Lo que el usuario escribe ("AP", "TSJ", "JM")
# ---------------------------------------------------------------------------

ALIAS_ORGANO: dict[str, list[str]] = {
    "TS": ["11", "12", "13", "14", "15", "16"],
    "AN": ["22", "2264", "23", "24", "25", "26", "27", "28", "29"],
    "TSJ": ["31", "31201202", "33", "34"],
    "AP": ["37", "38"],
    "AT": ["36"],
    "JPI": ["42"],
    "JPII": ["41"],
    "JI": ["43"],
    "JS": ["44"],
    "JCA": ["45"],
    "JM": ["47"],
    "JVM": ["48"],
    "JF": ["50"],
    "JP": ["51"],
    "JVP": ["52"],
    "JMEN": ["53"],
    "MILITAR": ["75", "83", "85"],
    "MARCA": ["1001", "1002"],
}

# ---------------------------------------------------------------------------
# Jurisdicciones -> codigos de organo
# ---------------------------------------------------------------------------

JURISDICCIONES: dict[str, list[str]] = {
    "CIVIL": ["11", "31", "37", "41", "42", "47", "50"],
    "PENAL": ["12", "22", "2264", "27", "28", "31", "31201202", "37", "38",
              "43", "48", "51", "52", "53"],
    "CONTENCIOSO": ["13", "23", "29", "33", "45"],
    "SOCIAL": ["14", "24", "34", "44"],
    "MILITAR": ["15", "75", "83", "85"],
}

# ---------------------------------------------------------------------------
# Provincias -> siglas usadas en el ROJ y en el ECLI de las AP/TSJ
# (SAP VA 863/2026 -> ECLI:ES:APVA:2026:863)
# ---------------------------------------------------------------------------

PROVINCIAS: dict[str, str] = {
    "ALAVA": "VI", "ARABA": "VI",
    "ALBACETE": "AB",
    "ALICANTE": "A", "ALACANT": "A",
    "ALMERIA": "AL",
    "ASTURIAS": "O", "OVIEDO": "O",
    "AVILA": "AV",
    "BADAJOZ": "BA",
    "BALEARES": "IB", "ILLES BALEARS": "IB", "PALMA": "IB",
    "BARCELONA": "B",
    "BURGOS": "BU",
    "CACERES": "CC",
    "CADIZ": "CA",
    "CANTABRIA": "S", "SANTANDER": "S",
    "CASTELLON": "CS",
    "CEUTA": "CE",
    "CIUDAD REAL": "CR",
    "CORDOBA": "CO",
    "A CORUNA": "C", "LA CORUNA": "C", "CORUNA": "C",
    "CUENCA": "CU",
    "GIRONA": "GI", "GERONA": "GI",
    "GRANADA": "GR",
    "GUADALAJARA": "GU",
    "GIPUZKOA": "SS", "GUIPUZCOA": "SS", "SAN SEBASTIAN": "SS",
    "HUELVA": "H",
    "HUESCA": "HU",
    "JAEN": "J",
    "LEON": "LE",
    "LLEIDA": "L", "LERIDA": "L",
    "LA RIOJA": "LO", "RIOJA": "LO", "LOGRONO": "LO",
    "LUGO": "LU",
    "MADRID": "M",
    "MALAGA": "MA",
    "MELILLA": "ML",
    "MURCIA": "MU",
    "NAVARRA": "NA", "PAMPLONA": "NA",
    "OURENSE": "OU", "ORENSE": "OU",
    "PALENCIA": "P",
    "LAS PALMAS": "GC", "PALMAS": "GC",
    "PONTEVEDRA": "PO", "VIGO": "PO",
    "SALAMANCA": "SA",
    "SANTA CRUZ DE TENERIFE": "TF", "TENERIFE": "TF",
    "SEGOVIA": "SG",
    "SEVILLA": "SE",
    "SORIA": "SO",
    "TARRAGONA": "T",
    "TERUEL": "TE",
    "TOLEDO": "TO",
    "VALENCIA": "V", "VALENCIA/VALENCIA": "V",
    "VALLADOLID": "VA",
    "BIZKAIA": "BI", "VIZCAYA": "BI", "BILBAO": "BI",
    "ZAMORA": "ZA",
    "ZARAGOZA": "Z",
}


def _norm(texto: str) -> str:
    """Normaliza para buscar en las tablas: mayusculas y sin tildes."""
    import unicodedata

    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.upper().strip()


def codigos_por_tipo_organo(tipo: str) -> list[str]:
    """Traduce 'AP', 'TSJ', 'JM'... o un codigo literal a lista de codigos.

    Devuelve [] si no se reconoce, para que el llamante decida.
    """
    t = _norm(tipo)
    if not t:
        return []
    if t in ALIAS_ORGANO:
        return ALIAS_ORGANO[t]
    if t in ORGANOS:  # ya es un codigo oficial
        return [t]
    return []


def codigos_por_jurisdiccion(jurisdiccion: str) -> list[str]:
    """Traduce 'CIVIL', 'PENAL'... a lista de codigos de organo."""
    return JURISDICCIONES.get(_norm(jurisdiccion), [])


def sigla_provincia(nombre: str) -> str | None:
    """'Valladolid' -> 'VA'. Acepta ya la sigla ('VA' -> 'VA')."""
    n = _norm(nombre)
    if not n:
        return None
    if n in PROVINCIAS:
        return PROVINCIAS[n]
    if n in set(PROVINCIAS.values()):
        return n
    return None


def nombre_organo(codigo: str) -> str:
    """Descripcion legible de un codigo de organo."""
    return ORGANOS.get(str(codigo), f"ORGANO {codigo}")
