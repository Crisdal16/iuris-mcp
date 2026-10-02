"""Parseo y normalizacion de identificadores de resoluciones judiciales.

Tres identificadores conviven en el CENDOJ:

  ROJ        "STS 1177/2014", "SAP VA 863/2026", "AAP B 9672/2019"
  ECLI       "ECLI:ES:TS:2014:1177", "ECLI:ES:APB:2019:9672A"
  Id Cendoj  "28079140012014100117"  (20 digitos)

REGLA CRITICA (verificada contra el CENDOJ): los AUTOS comparten numero con la
sentencia homonima y se distinguen SOLO por una 'A':

    AAP B 9672/2019  <->  ECLI:ES:APB:2019:9672A     (auto)
    SAP B 9672/2019  <->  ECLI:ES:APB:2019:9672      (sentencia)

Perder esa 'A' final abre un documento distinto. Por eso `es_auto` viaja en el
dataclass y `a_ecli()` la vuelve a escribir siempre.

El Id Cendoj se descompone en: municipio INE(5) + organo(2) + seccion(3) +
anio(4) + serial(6). Ej.: 28079 14 001 2014 100117
                          Madrid | TS Social | secc. 1 | 2014 | serial
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .organos import nombre_organo

# ---------------------------------------------------------------------------
# Tipos de resolucion en el ROJ: la inicial S = Sentencia, A = Auto.
# El resto identifica el organo. Mapea al codigo de tribunal usado en el ECLI.
# ---------------------------------------------------------------------------

_ROJ_A_ECLI: dict[str, str] = {
    "TS": "TS",
    "AN": "AN",
    "TC": "TC",
    "TSJ": "TSJ",   # + sigla de provincia -> TSJM, TSJVA...
    "AP": "AP",     # + sigla de provincia -> APB, APVA...
    "JPI": "JPI",
    "JPII": "JPII",
    "JI": "JI",
    "JM": "JM",
    "JSO": "JSO",
    "JCA": "JCA",
    "JP": "JP",
    "JVM": "JVM",
    "JMEN": "JMEN",
    "JVP": "JVP",
    "TMT": "TMT",
    "TMC": "TMC",
}

# Organos cuyo ECLI NO lleva sigla de provincia
_SIN_PROVINCIA = {"TS", "AN", "TC"}

_RE_ECLI = re.compile(
    r"^ECLI:(?P<pais>ES|EU):(?P<tribunal>[A-Z0-9]+):(?P<anio>\d{4}):"
    r"(?P<numero>\d+)(?P<auto>A?)$",
    re.IGNORECASE,
)

# "STS 1177/2014" | "SAP VA 863/2026" | "AAP B 9672/2019" | "STC 31/2010"
_RE_ROJ = re.compile(
    r"^(?P<clase>[SA])(?P<organo>TSJ|TS|AN|TC|AP|JPII|JPI|JI|JM|JSO|JCA|JP|"
    r"JVM|JMEN|JVP|TMT|TMC)"
    r"(?:\s+(?P<provincia>[A-Z]{1,3}))?"
    r"\s+(?P<numero>\d+)\s*/\s*(?P<anio>\d{4})$",
    re.IGNORECASE,
)

_RE_ID_CENDOJ = re.compile(r"^\d{20}$")

# Asunto del TJUE: "C-311/19", "T-778/16"
_RE_ASUNTO_UE = re.compile(r"^(?P<sala>[CT])\s*-\s*(?P<numero>\d+)\s*/\s*(?P<anio>\d{2,4})$",
                           re.IGNORECASE)


@dataclass(frozen=True)
class Ecli:
    pais: str          # "ES" | "EU"
    tribunal: str      # "TS", "APB", "TSJM", "C", "T"...
    anio: int
    numero: str
    es_auto: bool

    def __str__(self) -> str:
        return f"ECLI:{self.pais}:{self.tribunal}:{self.anio}:{self.numero}" + (
            "A" if self.es_auto else ""
        )


@dataclass(frozen=True)
class Roj:
    clase: str         # "S" (sentencia) | "A" (auto)
    organo: str        # "TS", "AP", "TSJ"...
    provincia: str | None
    numero: str
    anio: int

    @property
    def es_auto(self) -> bool:
        return self.clase.upper() == "A"

    def __str__(self) -> str:
        prov = f" {self.provincia}" if self.provincia else ""
        return f"{self.clase}{self.organo}{prov} {self.numero}/{self.anio}"


@dataclass(frozen=True)
class IdCendoj:
    bruto: str
    municipio: str     # codigo INE, 5 digitos
    organo: str        # 2 digitos
    seccion: str       # 3 digitos
    anio: int
    serial: str        # 6 digitos

    @property
    def descripcion_organo(self) -> str:
        return nombre_organo(self.organo)

    def __str__(self) -> str:
        return self.bruto


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_ecli(cita: str) -> Ecli | None:
    """'ECLI:ES:APB:2019:9672A' -> Ecli(..., es_auto=True). None si no encaja."""
    m = _RE_ECLI.match(cita.strip())
    if not m:
        return None
    return Ecli(
        pais=m.group("pais").upper(),
        tribunal=m.group("tribunal").upper(),
        anio=int(m.group("anio")),
        numero=m.group("numero"),
        es_auto=bool(m.group("auto")),
    )


def parse_roj(cita: str) -> Roj | None:
    """'SAP VA 863/2026' -> Roj(clase='S', organo='AP', provincia='VA', ...)."""
    m = _RE_ROJ.match(" ".join(cita.strip().split()))
    if not m:
        return None
    prov = m.group("provincia")
    return Roj(
        clase=m.group("clase").upper(),
        organo=m.group("organo").upper(),
        provincia=prov.upper() if prov else None,
        numero=m.group("numero"),
        anio=int(m.group("anio")),
    )


def parse_id_cendoj(valor: str) -> IdCendoj | None:
    """'28079140012014100117' -> IdCendoj(municipio='28079', organo='14', ...)."""
    v = valor.strip().replace(" ", "")
    if not _RE_ID_CENDOJ.match(v):
        return None
    return IdCendoj(
        bruto=v,
        municipio=v[0:5],
        organo=v[5:7],
        seccion=v[7:10],
        anio=int(v[10:14]),
        serial=v[14:20],
    )


def roj_a_ecli(roj: Roj) -> Ecli | None:
    """Convierte un ROJ en su ECLI. Conserva la marca de AUTO."""
    base = _ROJ_A_ECLI.get(roj.organo)
    if base is None:
        return None
    if base in _SIN_PROVINCIA:
        tribunal = base
    else:
        if not roj.provincia:
            return None
        tribunal = f"{base}{roj.provincia}"
    return Ecli(
        pais="ES",
        tribunal=tribunal,
        anio=roj.anio,
        numero=roj.numero,
        es_auto=roj.es_auto,
    )


def normalizar_cita(cita: str) -> Ecli | Roj | IdCendoj | str | None:
    """Punto de entrada unico: detecta que clase de identificador es.

    Devuelve el dataclass correspondiente, o el asunto UE normalizado como str
    ('C-311/19'), o None si no se reconoce nada.
    """
    c = " ".join(cita.strip().split())
    if not c:
        return None
    for parser in (parse_ecli, parse_roj, parse_id_cendoj):
        resultado = parser(c)
        if resultado is not None:
            return resultado
    m = _RE_ASUNTO_UE.match(c)
    if m:
        anio = m.group("anio")
        return f"{m.group('sala').upper()}-{m.group('numero')}/{anio}"
    return None


def separar_citas(texto: str) -> list[str]:
    """Parte 'STS 1177/2014, ECLI:ES:TS:2014:4786' en citas sueltas.

    Solo separa por comas y saltos de linea: los ROJ llevan espacios dentro
    ('SAP VA 863/2026'), asi que no se puede partir por espacios.
    """
    trozos = re.split(r"[,\n;]+", texto)
    return [" ".join(t.split()) for t in trozos if t.strip()]
