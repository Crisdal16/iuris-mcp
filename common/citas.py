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
# En texto libre solo el formato real de los asuntos (año de 2 cifras, C/T en
# mayuscula): 'C-1/2020' o 'c-3/21' suelen ser anexos o expedientes, no asuntos.
_RE_ASUNTO = re.compile(r"\b(?:[Aa]sunto\s+)?([CT])\s*[-‑]\s*(\d{1,4})\s*/\s*(\d{2})\b(?![/\d])")
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
# Rango + numero. El lookbehind evita leer 'RD-ley 8/2020' o 'Decreto-ley 1/2021'
# como 'Ley 8/2020' (otra norma). Los decretos-leyes autonomicos se reconocen
# para poder marcarlos, no para resolverlos en el BOE estatal.
_RANGO_NUM = (r"(?<![\w-])(?:Ley\s+Org[aá]nica|L\.?\s?O\.?|Real\s+Decreto\s+Legislativo|RDLeg\.?|"
              r"Real\s+Decreto[\s-]+[Ll]ey|RD[\s-]+[Ll]ey|RDL|Real\s+Decreto|RD|"
              r"Decreto[\s-]+[Ll]ey|Decreto\s+Legislativo|Ley\s+Foral|Ley)\s+\d{1,4}/\d{4}")
_UE_REF = r"(?:Reglamento|Directiva|Decisi[oó]n)\s*(?:\((?:UE|CE|CEE)\)\s*)?(?:n[ºo°]\s*)?\d{2,4}/\d{1,4}(?:/(?:CEE|CE|UE|JAI))?"

_NUM_ART = r"\d{1,4}(?:\.\d{3}(?![\d]))?(?:\s*(?:bis|ter|quater|quinquies|sexies))?(?:\.\d+)*"
_RE_ARTICULO = re.compile(
    r"\b(?:art[ií]culos?|arts?\.|art\.?)\s*"
    r"(?P<nums>" + _NUM_ART + r"(?:\s*(?:,|y|e|o)\s*" + _NUM_ART + r")*)"
    r"(?=(?P<resto>[^\n;]{0,160}))",   # lookahead: no consume la cita siguiente
    re.IGNORECASE,
)
_RE_NORMA_EN_RESTO = re.compile(
    r"(?P<rango>" + _RANGO_NUM + r")|(?P<ue>" + _UE_REF + r")|"
    r"\b(?P<nombre>" + "|".join(re.escape(n) for n in sorted(_NOMBRES, key=len, reverse=True)) + r")\b|"
    r"\b(?P<sigla>" + "|".join(_SIGLAS) + r")\b",
    re.IGNORECASE,
)
# Lo que puede haber entre el numero del articulo y su norma: apartados, letras,
# ordinales y 'de la' / 'del'. Si hay otra cosa ('del convenio, conforme al'),
# la sigla que aparezca despues no es la norma de ese articulo.
_RE_HUECO = re.compile(
    r"^(?:[OA]\b)?"                    # el 'º' de '2º' llega como 'O' tras normalizar
    r"[\s,.;:()ºª°\d\-]*(?:(?<=\d)[OA]\b[\s,.]*)?"
    r"(?:(?:APARTADOS?|APDOS?\.?|PARRAFOS?|LETRAS?|NUMEROS?|N\.?[O°º]\.?|ORDINAL|INCISO|PUNTO)"
    r"\s*[\w.ºª°]{1,6}\)?[\s,.]*(?:(?:Y|E)\s+[\w.ºª°]{1,6}\)?[\s,.]*)?)*"
    r"(?:DE\s+LA|DEL|DE|EN\s+LA|EN\s+EL)?\s*(?:VIGENTE|CITAD[OA]|REFERID[OA])?\s*$"
)
_RE_AUTONOMICA = re.compile(
    r"\b(AUTONOMIC|FORAL|COMUNIDAD\s+AUTONOMA|DE\s+LA\s+COMUNIDAD|PRINCIPADO|"
    r"GALICIA|CATALUNA|ANDALUCIA|ARAGON|ASTURIAS|BALEARS|BALEARES|CANARIAS|CANTABRIA|"
    r"CASTILLA|EXTREMADURA|LA\s+RIOJA|MADRID|MURCIA|NAVARRA|PAIS\s+VASCO|EUSKADI|"
    r"VALENCIANA|CEUTA|MELILLA|DEL\s+PARLAMENTO\s+DE)")
_MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
          "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
          "DICIEMBRE": 12}
_RE_FECHA_NORMA = re.compile(r"^\s*,?\s*DE\s+(\d{1,2})\s+DE\s+(" + "|".join(_MESES) + r")\b")
_RE_SIGUE = re.compile(
    r"^\s*(?:,|Y|E)\s*(?:EL\s+|LOS\s+|DEL\s+|ART[IÍ]CULOS?\s*|ARTS?\.\s*)?"
    r"(?P<nums>" + _NUM_ART + r"(?:\s*(?:,|Y|E)\s*" + _NUM_ART + r")*)", re.IGNORECASE)
_RE_NO_ART = re.compile(r"^\s*(DIAS|MESES|ANOS|SEMANAS|HORAS|EUROS|POR\s+CIENTO|%)\b")


def _sin_millar(n: str) -> str:
    """'1.902' -> '1902' (punto de millar, habitual en los escritos). '394.1' no cambia."""
    return re.sub(r"(?<![\d.])(\d)\.(\d{3})(?![\d.])", r"\1\2", n)


def _numeros(nums: str) -> list[str]:
    out = []
    for n in re.split(r"\s*(?:,|\by\b|\be\b|\bo\b)\s*", nums, flags=re.IGNORECASE):
        n = " ".join(_sin_millar(n).split())
        if not n:
            continue
        base = n.split(".")[0]           # 394.1 -> 394 (el apartado no cambia el articulo)
        if base not in out:
            out.append(base)
    return out


def _sin_tildes(t: str) -> str:
    """Mayusculas sin tildes conservando la longitud (para reutilizar posiciones)."""
    return "".join(norm(ch)[:1] or ch for ch in t)


@dataclass
class _Norma:
    texto: str = ""        # 'LEC', 'Ley 29/1998', 'Directiva 93/13/CEE'...
    fin: int = 0           # posicion en `resto` justo despues de la norma
    autonomica: bool = False
    fecha: str = ""        # 'DD/MM' si la cita trae ', de 13 de julio'


def _norma_de(resto: str) -> _Norma:
    # Se busca sobre el texto sin tildes ('Código' == 'CODIGO') pero se devuelve
    # el trozo original.
    plano = _sin_tildes(resto)
    m = _RE_NORMA_EN_RESTO.search(plano)
    if not m or not _RE_HUECO.match(plano[: m.start()]):
        return _Norma()
    n = _Norma(fin=m.end())
    if m.group("rango"):
        n.texto = " ".join(resto[m.start("rango"):m.end("rango")].split())
        tras = plano[m.end():m.end() + 120]
        f = _RE_FECHA_NORMA.match(tras)
        if f:
            n.fecha = f"{int(f.group(1)):02d}/{_MESES[f.group(2)]:02d}"
        hasta = re.search(r"\bART|[;\n]", tras)
        cola = tras[: hasta.start()] if hasta else tras
        if (_RE_AUTONOMICA.search(cola) or
                re.match(r"(?i)(Decreto[\s-]+ley|Decreto\s+Legislativo|Ley\s+Foral)", n.texto)):
            n.autonomica = True
    elif m.group("ue"):
        n.texto = " ".join(resto[m.start("ue"):m.end("ue")].split())
    elif m.group("nombre"):
        nombre = m.group("nombre")
        # 'constitución de la sociedad' no es la Constitucion: exige mayuscula.
        if nombre == "CONSTITUCION" and not resto[m.start("nombre")].isupper():
            return _Norma()
        n.texto = _NOMBRES[nombre]
    else:
        n.texto = m.group("sigla").upper()
    return n


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
        nums, resto = m.group("nums"), m.group("resto")
        contexto = _contexto(texto, m.start(), m.end())
        # 'el artículo 7, 15 días después': el 15 no es un articulo.
        partes = re.split(r"(\s*(?:,|\by\b|\be\b|\bo\b)\s*)", nums)
        if len(partes) > 1 and _RE_NO_ART.match(_sin_tildes(resto)):
            nums = "".join(partes[:-2])
        # Enumeraciones con normas distintas: 'art. 18 de la LOPJ y 19 LEC'.
        for _ in range(6):
            norma = _norma_de(resto)
            for n in _numeros(nums):
                add(Cita("articulo", f"{n} {norma.texto}".strip(), f"art. {n} {norma.texto}".strip(),
                         norma=norma.texto, articulo=n, contexto=contexto, posicion=m.start(),
                         extra={"autonomica": norma.autonomica, "fecha": norma.fecha}))
            if not norma.texto:
                break
            sigue = _RE_SIGUE.match(_sin_tildes(resto[norma.fin:]))
            if not sigue:
                break
            nums = resto[norma.fin + sigue.start("nums"):norma.fin + sigue.end("nums")]
            resto = resto[norma.fin + sigue.end():]

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
        if norma.texto and nums:
            return Cita("articulo", f"{nums[0]} {norma.texto}", c, norma=norma.texto,
                        articulo=nums[0],
                        extra={"autonomica": norma.autonomica, "fecha": norma.fecha})

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


def es_norma_ue(norma: str) -> bool:
    """True solo para actos de la UE: alias conocido (RGPD...), CELEX o
    'Reglamento/Directiva/Decision' con numero. 'Reglamento Hipotecario' o
    'Reglamento del Registro Mercantil' son normas espanolas (BOE)."""
    from sources.deep_links import a_celex

    n = (norma or "").strip()
    if not n or not re.match(r"(?i)(Reglamento|Directiva|Decisi|RGPD|GDPR|\d)", n):
        return False
    return a_celex(n) is not None
