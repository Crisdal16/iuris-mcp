"""Reconocimiento de citas juridicas (sin red).

Dos usos:
  * `clasificar(cita)`: dice a que fuente pertenece UNA cita suelta
    (STC 31/2010, ECLI:..., C-311/18, BOE-A-..., V0282-26, 'art. 1902 CC'...)
    para que buscar_por_cita la abra con la tool correcta.
  * `extraer_citas(texto)`: localiza TODAS las citas de un escrito (articulos
    de ley con su norma, resoluciones judiciales, consultas DGT, RG del TEAC)
    para verificar_escrito.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from common.cendoj_ids import Ecli, IdCendoj, Roj, normalizar_cita
from common.texto import norm


@dataclass
class Cita:
    tipo: str            # articulo | tc | tjue | cendoj | id_cendoj | boe | dgt | teac | norma_ue
    ref: str             # referencia normalizada para la tool de destino
    original: str = ""   # tal como aparece en el texto
    norma: str = ""      # solo articulos: sigla / 'Ley 29/1998' / 'RGPD'...
    articulo: str = ""   # solo articulos
    contexto: str = ""   # frase del escrito donde aparece (lo que el escrito AFIRMA)
    posicion: int = 0
    extra: dict = field(default_factory=dict)


# --- Patrones ----------------------------------------------------------------

_RE_BOE = re.compile(r"\bBOE-A-\d{4}-\d+\b", re.IGNORECASE)
_RE_DGT = re.compile(r"\b[VG]\d{4}-\d{2}\b")
_RE_TEAC = re.compile(r"\b(?:RG|R\.G\.)?\s*(\d{2}/\d{5}/\d{4})\b")
_RE_ECLI = re.compile(r"\bECLI:(?:ES|EU):[A-Z0-9]+:\d{4}:\d+A?\b", re.IGNORECASE)
_RE_ASUNTO = re.compile(r"\b(?:asunto\s+)?([CT])\s*[-‑]\s*(\d{1,4})\s*/\s*(\d{2}|\d{4})\b(?!/)", re.IGNORECASE)
_RE_CELEX_JUR = re.compile(r"^6\d{4}[A-Z]{2}\d{4}$")
_RE_CELEX_NORMA = re.compile(r"^3\d{4}[A-Z]\d{3,4}$")
# Resoluciones con ROJ / cita breve: STS 1177/2014, SAP VA 863/2026, STC 31/2010, ATS 12/2020
_RE_ROJ = re.compile(
    r"\b([SA](?:TSJ|TS|AN|TC|AP|JPII|JPI|JI|JM|JSO|JCA|JP|JVM|JMEN|JVP))"
    r"(?:\s+([A-Z]{1,3}))?\s+(\d{1,6})\s*/\s*(\d{4})\b"
)

# Normas que pueden acompanar a un articulo. El orden importa: lo mas largo primero.
_SIGLAS = (
    "LECRIM", "LOPDGDD", "TRLGDCU", "LGDCU", "LOPJM", "LOREG", "LOPJ", "LOTC", "LJCA", "LRJS",
    "LRJSP", "LPAC", "LGSS", "LCSP", "LBRL", "LIRPF", "LIVA", "TRLC", "LSC", "LGT", "LAU",
    "LPH", "LEC", "LRC", "LJV", "LIS", "CCOM", "LH", "LC", "CC", "CP", "CE", "ET",
    "RGPD", "GDPR",
)
_NOMBRES = {
    "CODIGO CIVIL": "CC", "CODIGO PENAL": "CP", "CODIGO DE COMERCIO": "CCOM",
    "CONSTITUCION ESPANOLA": "CE", "CONSTITUCION": "CE",
    "LEY DE ENJUICIAMIENTO CIVIL": "LEC", "LEY DE ENJUICIAMIENTO CRIMINAL": "LECRIM",
    "ESTATUTO DE LOS TRABAJADORES": "ET", "LEY GENERAL TRIBUTARIA": "LGT",
    "LEY DE ARRENDAMIENTOS URBANOS": "LAU", "LEY DE PROPIEDAD HORIZONTAL": "LPH",
    "LEY DE SOCIEDADES DE CAPITAL": "LSC", "LEY HIPOTECARIA": "LH",
    "LEY ORGANICA DEL PODER JUDICIAL": "LOPJ",
    "LEY REGULADORA DE LA JURISDICCION SOCIAL": "LRJS",
    "LEY DE LA JURISDICCION CONTENCIOSO-ADMINISTRATIVA": "LJCA",
    "LEY GENERAL DE LA SEGURIDAD SOCIAL": "LGSS",
    "REGLAMENTO GENERAL DE PROTECCION DE DATOS": "RGPD",
}
_RANGO_NUM = (r"(?:Ley\s+Org[aá]nica|L\.?\s?O\.?|Real\s+Decreto\s+Legislativo|RDLeg\.?|"
              r"Real\s+Decreto[\s-]+[Ll]ey|RDL|Real\s+Decreto|RD|Ley)\s+\d{1,4}/\d{4}")
_UE_REF = r"(?:Reglamento|Directiva|Decisi[oó]n)\s*(?:\((?:UE|CE|CEE)\)\s*)?(?:n[ºo°]\s*)?\d{2,4}/\d{1,4}(?:/(?:CEE|CE|UE|JAI))?"

_NUM_ART = r"\d{1,4}(?:\s*(?:bis|ter|quater|quinquies|sexies))?(?:\.\d+)*"
_RE_ARTICULO = re.compile(
    r"\b(?:art[ií]culos?|arts?\.|art\.?)\s*"
    r"(?P<nums>" + _NUM_ART + r"(?:\s*(?:,|y|e|o)\s*" + _NUM_ART + r")*)"
    r"(?=(?P<resto>[^\n;]{0,90}))",   # lookahead: no consume la cita siguiente
    re.IGNORECASE,
)
_RE_NORMA_EN_RESTO = re.compile(
    r"(?P<rango>" + _RANGO_NUM + r")|(?P<ue>" + _UE_REF + r")|"
    r"(?P<nombre>" + "|".join(re.escape(n) for n in sorted(_NOMBRES, key=len, reverse=True)) + r")|"
    r"\b(?P<sigla>" + "|".join(_SIGLAS) + r")\b",
    re.IGNORECASE,
)


def _numeros(nums: str) -> list[str]:
    out = []
    for n in re.split(r"\s*(?:,|\by\b|\be\b|\bo\b)\s*", nums, flags=re.IGNORECASE):
        n = " ".join(n.split())
        if not n:
            continue
        base = n.split(".")[0]           # 394.1 -> 394 (el apartado no cambia el articulo)
        if base not in out:
            out.append(base)
    return out


def _sin_tildes(t: str) -> str:
    """Mayusculas sin tildes conservando la longitud (para reutilizar posiciones)."""
    return "".join(norm(ch)[:1] or ch for ch in t)


def _norma_de(resto: str) -> str:
    # Se busca sobre el texto sin tildes ('Código' == 'CODIGO') pero se devuelve
    # el trozo original. Si antes de la norma hay otra referencia a articulo, la
    # norma es de esa otra cita, no de la nuestra.
    plano = _sin_tildes(resto)
    m = _RE_NORMA_EN_RESTO.search(plano)
    if not m:
        return ""
    if re.search(r"\bART", plano[: m.start()]):
        return ""
    if m.group("rango"):
        return " ".join(resto[m.start("rango"):m.end("rango")].split())
    if m.group("ue"):
        return " ".join(resto[m.start("ue"):m.end("ue")].split())
    if m.group("nombre"):
        return _NOMBRES[m.group("nombre")]
    return m.group("sigla").upper()


def _contexto(texto: str, ini: int, fin: int) -> str:
    """La frase que contiene la cita (lo que el escrito dice de ella)."""
    a = max(texto.rfind(".", 0, max(0, ini - 1)), texto.rfind("\n", 0, ini)) + 1
    m = re.search(r"[.\n]", texto[fin:])
    b = fin + (m.start() + 1 if m else len(texto) - fin)
    frase = " ".join(texto[a:b].split())
    return frase[:400]


def extraer_citas(texto: str) -> list[Cita]:
    """Todas las citas de un escrito, en orden de aparicion y sin duplicados."""
    citas: list[Cita] = []
    vistos: set[tuple[str, str]] = set()

    def add(c: Cita) -> None:
        clave = (c.tipo, c.ref.upper())
        if clave in vistos:
            return
        vistos.add(clave)
        citas.append(c)

    for m in _RE_ARTICULO.finditer(texto):
        norma = _norma_de(m.group("resto"))
        for n in _numeros(m.group("nums")):
            add(Cita("articulo", f"{n} {norma}".strip(), m.group(0)[:80].strip(), norma=norma,
                     articulo=n, contexto=_contexto(texto, m.start(), m.end()), posicion=m.start()))

    for m in _RE_ECLI.finditer(texto):
        c = clasificar(m.group(0))
        if c:
            c.original, c.posicion = m.group(0), m.start()
            c.contexto = _contexto(texto, m.start(), m.end())
            add(c)
    for m in _RE_ROJ.finditer(texto):
        bruto = m.group(0)
        c = clasificar(bruto)
        if c:
            c.original, c.posicion = bruto, m.start()
            c.contexto = _contexto(texto, m.start(), m.end())
            add(c)
    for m in _RE_ASUNTO.finditer(texto):
        ref = f"{m.group(1).upper()}-{m.group(2)}/{m.group(3)}"
        add(Cita("tjue", ref, m.group(0), contexto=_contexto(texto, m.start(), m.end()),
                 posicion=m.start()))
    for rx, tipo in ((_RE_BOE, "boe"), (_RE_DGT, "dgt")):
        for m in rx.finditer(texto):
            add(Cita(tipo, m.group(0).upper(), m.group(0),
                     contexto=_contexto(texto, m.start(), m.end()), posicion=m.start()))
    for m in _RE_TEAC.finditer(texto):
        add(Cita("teac", m.group(1), m.group(0).strip(),
                 contexto=_contexto(texto, m.start(), m.end()), posicion=m.start()))

    citas.sort(key=lambda c: c.posicion)
    return citas


def clasificar(cita: str) -> Cita | None:
    """A que fuente va UNA cita suelta. None si no se reconoce."""
    c = " ".join((cita or "").strip().split())
    if not c:
        return None
    u = c.upper()

    if _RE_BOE.fullmatch(u):
        return Cita("boe", u, c)
    if _RE_DGT.fullmatch(u):
        return Cita("dgt", u, c)
    m = re.fullmatch(r"(?:RG|R\.G\.)?\s*(\d{2}/\d{5}/\d{4})", u)
    if m:
        return Cita("teac", m.group(1), c)
    if _RE_CELEX_JUR.match(u):
        return Cita("tjue", u, c)
    if _RE_CELEX_NORMA.match(u):
        return Cita("norma_ue", u, c)

    # 'art. 1902 CC', 'articulo 24 de la Constitucion', 'art. 17 RGPD'
    m = _RE_ARTICULO.match(c)
    if m:
        norma = _norma_de(m.group("resto"))
        nums = _numeros(m.group("nums"))
        if norma and nums:
            return Cita("articulo", f"{nums[0]} {norma}", c, norma=norma, articulo=nums[0])

    obj = normalizar_cita(c)
    if isinstance(obj, Ecli):
        if obj.pais == "EU":
            return Cita("tjue", str(obj), c)
        if obj.tribunal == "TC":
            return Cita("tc", str(obj), c)
        return Cita("cendoj", str(obj), c, extra={"ecli": str(obj)})
    if isinstance(obj, Roj):
        if obj.organo.upper() == "TC":
            tipo = "STC" if obj.clase.upper() == "S" else "ATC"
            return Cita("tc", f"{tipo} {obj.numero}/{obj.anio}", c)
        return Cita("cendoj", str(obj), c, extra={"roj": str(obj)})
    if isinstance(obj, IdCendoj):
        return Cita("id_cendoj", str(obj), c)
    if isinstance(obj, str):          # asunto UE ya normalizado
        return Cita("tjue", obj, c)
    if re.fullmatch(r"DTC\s*\d+/\d{4}", u):
        return Cita("tc", u, c)

    # Norma suelta: 'Ley 29/1998', 'Directiva 93/13/CEE', 'RGPD'
    if re.fullmatch(_RANGO_NUM, c, re.IGNORECASE):
        return Cita("norma", c, c, norma=c)
    if re.fullmatch(_UE_REF, c, re.IGNORECASE) or u in ("RGPD", "GDPR"):
        return Cita("norma_ue", c, c, norma=c)
    return None


_ES_UE = re.compile(r"^(Reglamento|Directiva|Decisi|RGPD|GDPR)", re.IGNORECASE)


def es_norma_ue(norma: str) -> bool:
    return bool(_ES_UE.match(norma or ""))
