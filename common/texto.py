"""Utilidades de texto compartidas por las fuentes de jurisprudencia (CENDOJ, TC,
TJUE): normalizacion, parrafos, busqueda de pasajes, nombres de fichero y
extraccion de texto limpio desde HTML."""

from __future__ import annotations

import os
import re
import unicodedata


def norm(texto: str) -> str:
    """Mayusculas y sin tildes, para comparar."""
    d = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in d if not unicodedata.combining(c)).upper().strip()


def parrafos(texto: str) -> list[str]:
    """Reagrupa lineas en parrafos (una linea que acaba en . : ; o una linea
    en mayusculas cierra parrafo; una linea en blanco tambien)."""
    out: list[str] = []
    actual: list[str] = []
    for linea in texto.splitlines():
        l = linea.strip()
        if not l:
            if actual:
                out.append(" ".join(actual))
                actual = []
            continue
        actual.append(l)
        if l[-1] in ".:;" or l.isupper():
            out.append(" ".join(actual))
            actual = []
    if actual:
        out.append(" ".join(actual))
    return [p for p in out if len(p) > 2]


def parrafos_con(texto: str, palabras_clave: str, maximo: int = 12) -> tuple[list[str], str]:
    """Parrafos que contienen TODAS las palabras clave (sin tildes ni mayusculas).
    Si ninguno las contiene todas, devuelve los que contienen ALGUNA.
    Devuelve (parrafos, modo) con modo 'todas' | 'alguna' | 'ninguna'."""
    claves = [norm(p) for p in re.split(r"[,\s]+", palabras_clave) if p.strip()]
    if not claves:
        return [], "ninguna"
    ps = parrafos(texto)
    todas = [p for p in ps if all(c in norm(p) for c in claves)]
    if todas:
        return todas[:maximo], "todas"
    alguna = [p for p in ps if any(c in norm(p) for c in claves)]
    return alguna[:maximo], ("alguna" if alguna else "ninguna")


def slug(s: str) -> str:
    """'STSJ MU 1411/2026' -> 'STSJ_MU_1411-2026' (nombre de fichero seguro)."""
    s = norm(s).replace("/", "-").replace(":", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "documento"


def dir_destino(ruta: str, por_defecto: str) -> str:
    """Carpeta donde guardar: `ruta` (carpeta o fichero) o `por_defecto`."""
    if ruta:
        ruta = os.path.expanduser(ruta)
        if os.path.isdir(ruta) or not os.path.splitext(ruta)[1]:
            os.makedirs(ruta, exist_ok=True)
            return ruta
        d = os.path.dirname(ruta) or "."
        os.makedirs(d, exist_ok=True)
        return d
    os.makedirs(por_defecto, exist_ok=True)
    return por_defecto


def texto_de_html(nodo) -> str:
    """Texto limpio de un nodo selectolax: sin scripts/estilos, una linea por
    bloque, sin espacios repetidos ni lineas vacias en cadena."""
    if nodo is None:
        return ""
    for s in nodo.css("script,style,noscript"):
        s.decompose()
    t = nodo.text(separator="\n")
    t = t.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def truncar(cuerpo: str, max_chars: int, total_doc: int, consejo: str, titulo: str = "") -> str:
    """Recorta al chat; el resto queda disponible via continuar_lectura."""
    from common import lecturas

    if len(cuerpo) <= max_chars:
        return cuerpo
    return lecturas.recortar(
        cuerpo, max_chars, titulo=titulo,
        consejo=f"Documento completo: {total_doc} caracteres. Para acotar: {consejo}",
    )
