"""Normativa de la UE (reglamentos, directivas, decisiones): texto en ESPANOL.

EUR-Lex bloquea a los clientes automatizados, pero el mismo documento se sirve
por CELLAR, la API publica de la Oficina de Publicaciones de la UE (la que ya
usa sources/tjue.py): `publications.europa.eu/resource/celex/<CELEX>`.

Ojo: CELLAR entrega el acto TAL COMO SE PUBLICO en el DOUE (version original),
no la version consolidada. Por eso la salida lo advierte y da el enlace al
consolidado de EUR-Lex para comprobar modificaciones posteriores.
"""

from __future__ import annotations

import re

from common.texto import norm
from sources import deep_links, tjue

_RE_FIN = re.compile(r"^(ANEXO|Hecho en |Por el Parlamento|Por el Consejo)", re.IGNORECASE)


def _clave(articulo: str) -> str:
    a = norm(articulo)
    a = re.sub(r"\bART(ICULO|\.)?\s*", "", a).strip(" .")
    return a


def extraer_articulo(texto: str, articulo: str) -> str | None:
    """Recorta 'Artículo N' (hasta el siguiente articulo, anexo o firma)."""
    objetivo = _clave(articulo)
    if not objetivo:
        return None
    lineas = texto.splitlines()
    inicio = None
    patron = re.compile(r"^ART[IÍ]CULO\s+(\d+\s*(?:BIS|TER|QUATER)?)\b\.?\s*(.*)$", re.IGNORECASE)
    for i, l in enumerate(lineas):
        m = patron.match(norm(l))
        if m and " ".join(m.group(1).split()) == objetivo:
            # Una cita interna ("articulo 6, apartado 1...") no es un rotulo:
            # el rotulo va solo en su linea o seguido de un epigrafe corto.
            if len(m.group(2)) > 120:
                continue
            inicio = i
            break
    if inicio is None:
        return None
    fin = len(lineas)
    for j in range(inicio + 1, len(lineas)):
        mj = patron.match(norm(lineas[j]))
        if (mj and len(mj.group(2)) <= 120) or _RE_FIN.match(lineas[j].strip()):
            fin = j
            break
    return "\n".join(lineas[inicio:fin]).strip()


def articulo_ue(referencia: str, articulo: str = "") -> str:
    """Texto en espanol de una norma UE (o de uno de sus articulos) via CELLAR."""
    celex = deep_links.a_celex(referencia)
    if not celex:
        return (
            f"No supe convertir «{referencia}» a CELEX. Indica el tipo y numero "
            "('Directiva 93/13/CEE', 'Reglamento (UE) 2016/679'), un alias (RGPD, "
            "Reglamento de IA) o el CELEX directo ('32016R0679')."
        )
    consolidado = deep_links.EURLEX.format(celex=celex)
    try:
        texto = tjue._descargar(celex)
    except Exception as e:  # noqa: BLE001
        texto = None
        error = f"{type(e).__name__}: {e}"
    else:
        error = "CELLAR no devolvio el documento en espanol"
    if not texto:
        return (f"No pude obtener {celex} de CELLAR ({error}).\n"
                f"Abre el texto en tu navegador: {consolidado}")

    aviso = (f"Fuente: CELLAR (Oficina de Publicaciones de la UE), CELEX {celex}. "
             f"Version ORIGINAL publicada en el DOUE; comprueba modificaciones en el "
             f"consolidado: {consolidado}")
    primeras = texto.splitlines()[:25]
    titulo = next((l for l in primeras if re.match(r"(REGLAMENTO|DIRECTIVA|DECISI)", norm(l))),
                  next((l for l in primeras if len(l) > 25 and "DIARIO OFICIAL" not in norm(l)),
                       celex))
    if articulo:
        bloque = extraer_articulo(texto, articulo)
        if bloque is None:
            return (f"No encontre el «artículo {articulo}» en {celex} ({titulo[:120]}).\n"
                    f"Revisa el numero o abre el texto: {consolidado}")
        return f"【{titulo[:200]}】\n\n{bloque}\n\n{aviso}"
    from common.lecturas import recortar

    cuerpo = recortar(texto, 30000, titulo=f"Norma UE {celex}",
                      consejo="Para un precepto concreto pasa `articulo`.")
    return f"【{titulo[:200]}】\n\n{cuerpo}\n\n{aviso}"
