"""Lectura por tramos de textos largos (sentencias, convenios, boletines).

Cuando una tool tiene que recortar lo que devuelve al chat, guarda el texto
completo de esa parte aqui (diskcache local, caduca a los 7 dias) y le da a
Claude un identificador corto para pedir el siguiente tramo con
`continuar_lectura(lectura, desde)`, sin volver a descargar ni a meter en el
contexto lo que ya leyo.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

_CADUCIDAD = 7 * 24 * 3600

try:
    from diskcache import Cache

    _DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "lecturas")
    _cache: Any = Cache(_DIR, size_limit=int(5e8))
except Exception:  # pragma: no cover
    _cache = None

# Respaldo en memoria si diskcache no esta disponible.
_memoria: dict[str, dict] = {}


def guardar(texto: str, titulo: str = "") -> str:
    """Guarda `texto` y devuelve su identificador de lectura (12 hex)."""
    ident = hashlib.sha1(texto.encode("utf-8", errors="replace")).hexdigest()[:12]
    valor = {"texto": texto, "titulo": titulo}
    try:
        if _cache is not None:
            _cache.set(ident, valor, expire=_CADUCIDAD)
            return ident
    except Exception:
        pass
    _memoria[ident] = valor
    return ident


def obtener(ident: str) -> dict | None:
    ident = (ident or "").strip().lower()
    try:
        if _cache is not None:
            v = _cache.get(ident)
            if v is not None:
                return v
    except Exception:
        pass
    return _memoria.get(ident)


def pista(ident: str, desde: int) -> str:
    return f"continuar_lectura(lectura='{ident}', desde={desde})"


def tramo(ident: str, desde: int = 0, max_chars: int = 45000) -> str:
    """Devuelve el tramo [desde, desde+max_chars) de una lectura guardada."""
    v = obtener(ident)
    if v is None:
        return (f"No encuentro la lectura «{ident}» (caduca a los 7 dias o no existe). "
                "Vuelve a pedir el documento con la tool de lectura original.")
    texto = v["texto"]
    total = len(texto)
    desde = max(0, int(desde or 0))
    max_chars = max(1, int(max_chars or 45000))
    if desde >= total:
        return f"La lectura «{ident}» tiene {total} caracteres; no hay nada a partir de {desde}."
    fin = min(total, desde + max_chars)
    # No cortar a mitad de palabra si se puede evitar.
    if fin < total:
        corte = texto.rfind("\n", desde + max_chars // 2, fin)
        if corte == -1:
            corte = texto.rfind(" ", desde + max_chars // 2, fin)
        if corte > desde:
            fin = corte
    cab = f"[{v.get('titulo') or 'Lectura'} — caracteres {desde}-{fin} de {total}]"
    cuerpo = texto[desde:fin]
    if fin < total:
        cuerpo += f"\n\n[…quedan {total - fin} caracteres. Siguiente tramo: {pista(ident, fin)}]"
    else:
        cuerpo += "\n\n[Fin del documento.]"
    return f"{cab}\n\n{cuerpo}"


def recortar(cuerpo: str, max_chars: int, titulo: str = "", consejo: str = "") -> str:
    """Recorta `cuerpo` a `max_chars` y, si sobra, deja preparado el siguiente tramo."""
    if len(cuerpo) <= max_chars:
        return cuerpo
    ident = guardar(cuerpo, titulo)
    primero = tramo(ident, 0, max_chars)
    # tramo() ya incluye la cabecera y la pista de continuacion.
    return primero + (f"\n[{consejo}]" if consejo else "")
