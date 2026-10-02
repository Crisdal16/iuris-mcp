"""Fuentes en modo 'humano en el bucle': normativa de la UE (EUR-Lex), Tribunal
Constitucional y TJUE.

Estas fuentes no ofrecen una API abierta limpia y/o aplican control anti-bot
(EUR-Lex responde 202 a clientes automatizados). Por eso, como con el CENDOJ,
el servidor NO descarga: prepara el identificador/enlace oficial estable y el
usuario lo abre en su navegador. El valor esta en traducir la referencia comun
(RGPD, 'Directiva 93/13/CEE') al CELEX correcto y montar el deep-link exacto.
"""

from __future__ import annotations

import re
import unicodedata

EURLEX = "https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{celex}"
TC = "https://hj.tribunalconstitucional.es/"
CURIA = "https://curia.europa.eu/juris/recherche.jsf?language=es"


def _norm(t: str) -> str:
    d = unicodedata.normalize("NFKD", t)
    return "".join(c for c in d if not unicodedata.combining(c)).upper().strip()


# Alias comunes -> CELEX
_ALIAS_CELEX = {
    "RGPD": "32016R0679",
    "GDPR": "32016R0679",
    "REGLAMENTO GENERAL DE PROTECCION DE DATOS": "32016R0679",
    "EUROORDEN": "32002F0584",
    "REGLAMENTO DE IA": "32024R1689",
    "REGLAMENTO DE INTELIGENCIA ARTIFICIAL": "32024R1689",
    "AI ACT": "32024R1689",
    "DIRECTIVA DE CLAUSULAS ABUSIVAS": "31993L0013",
}

_TIPO_LETRA = {"REGLAMENTO": "R", "DIRECTIVA": "L", "DECISION": "D"}

# CELEX ya formado: 3 2016 R 0679
_RE_CELEX = re.compile(r"^[0-9]{1}[0-9]{4}[A-Z][0-9]{3,4}$")
# "Directiva 93/13/CEE", "Reglamento (UE) 2016/679", "Decision 2002/584/JAI"
_RE_REF = re.compile(
    r"(?P<tipo>reglamento|directiva|decision|decisión)\s*"
    r"(?:\(\s*(?:ue|ce|cee|euratom)\s*\)\s*)?"
    r"(?P<a>\d{2,4})\s*/\s*(?P<b>\d{1,4})",
    re.IGNORECASE,
)


def a_celex(referencia: str) -> str | None:
    """'RGPD' / 'Directiva 93/13/CEE' / '32016R0679' -> CELEX normalizado."""
    r = referencia.strip()
    n = _norm(r)
    if _RE_CELEX.match(n):
        return n
    if n in _ALIAS_CELEX:
        return _ALIAS_CELEX[n]
    m = _RE_REF.search(r)
    if m:
        tipo = _norm(m.group("tipo")).replace("DECISIÓN", "DECISION")
        letra = _TIPO_LETRA.get(tipo)
        if not letra:
            return None
        a, b = m.group("a"), m.group("b")
        # En una referencia 'AAAA/NN' el AÑO es el numero de 4 cifras; si el
        # primero tiene 2 cifras (93/13) el año es el primero (1993).
        if len(a) == 4:
            anio, num = a, b
        elif len(b) == 4:
            anio, num = b, a
        else:
            anio = ("19" + a) if int(a) > 50 else ("20" + a.zfill(2))
            num = b
        return f"3{anio}{letra}{num.zfill(4)}"
    return None


def norma_ue(referencia: str, articulo: str = "") -> str:
    """Prepara el enlace EUR-Lex (texto consolidado en espanol) de una norma UE."""
    celex = a_celex(referencia)
    if not celex:
        return (
            f"No supe convertir «{referencia}» a CELEX. Indica el tipo y numero "
            f"('Directiva 93/13/CEE', 'Reglamento (UE) 2016/679') o el CELEX "
            f"directo ('32016R0679')."
        )
    url = EURLEX.format(celex=celex)
    extra = f"\nArticulo pedido: {articulo} (localizalo en el indice de la norma)." if articulo else ""
    return (
        f"Norma UE «{referencia}» → CELEX {celex}.\n"
        f"Abre el texto consolidado en espanol en tu navegador:\n  {url}{extra}\n"
        f"(EUR-Lex aplica control anti-bot al acceso automatizado; por eso el "
        f"enlace lo abres tu. Es la version oficial consolidada.)"
    )


def tc_buscar(consulta: str) -> str:
    """Prepara la busqueda en el Buscador de Jurisprudencia Constitucional (TC)."""
    consulta = " ".join(consulta.split())
    return (
        f"Busqueda en el Tribunal Constitucional para «{consulta}».\n"
        f"Abre el Buscador de Jurisprudencia Constitucional y escribe la consulta:\n"
        f"  {TC}\n"
        f"Cubre STC/ATC/DTC desde 1980. Si ya tienes la cita (p.ej. 'STC 31/2010' "
        f"o 'ECLI:ES:TC:2019:76'), pasa el ECLI a cendoj_analizar_cita para "
        f"verificarlo, o abrelo tambien desde el CENDOJ."
    )


def tjue_buscar(consulta: str) -> str:
    """Prepara la busqueda en CURIA (TJUE y Tribunal General)."""
    consulta = " ".join(consulta.split())
    return (
        f"Busqueda en el TJUE / Tribunal General para «{consulta}».\n"
        f"Abre el buscador CURIA (en espanol) y escribe la consulta o el asunto "
        f"(p.ej. 'C-311/19'):\n  {CURIA}\n"
        f"Para el texto de una sentencia por su ECLI europeo (ECLI:EU:C:...), "
        f"tambien puedes usar EUR-Lex."
    )
