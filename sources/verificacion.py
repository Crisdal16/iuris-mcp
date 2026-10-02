"""Abrir cualquier cita (buscar_por_cita) y verificar las citas de un escrito
(verificar_escrito), enrutando cada una a su fuente oficial.

Todo es LECTURA: nada se publica ni se modifica. La verificacion de un escrito
devuelve un dossier (estado de cada cita + texto vigente o ficha + la frase del
escrito que la invoca) para que Claude remate el diagnostico: si la cita existe
no basta, hay que comprobar que dice lo que el escrito afirma.
"""

from __future__ import annotations

import asyncio
import os
import re

from common import citas as _citas
from common.citas import Cita
from sources import boe, cendoj, cendoj_live, dgt, normativa_ue, tc, teac, tjue

# Prefijos con los que las fuentes indican que algo NO se ha encontrado / ha fallado.
_FALLOS = ("No ", "Indica", "TJUE: fallo", "TC: fallo", "CENDOJ:", "Identificador no valido",
           "Se descargo", "Encontre el art", "El BOE devolvio", "Sin ")
_DEROGADO = re.compile(r"\((?:Derogad[oa]|Anulad[oa])\)|^\s*Sin contenido\.?\s*$|queda sin contenido",
                       re.IGNORECASE | re.MULTILINE)


def _fallo(salida: str) -> bool:
    s = (salida or "").lstrip()
    return not s or s.startswith(_FALLOS) or s.startswith("'")


# ---------------------------------------------------------------------------
# Abrir una cita
# ---------------------------------------------------------------------------

def _articulo(norma: str, articulo: str) -> str:
    if _citas.es_norma_ue(norma):
        return normativa_ue.articulo_ue(norma, articulo)
    if not norma:
        return (f"La cita del artículo {articulo} no indica la norma. Usa "
                f"buscar_articulo('<norma>', '{articulo}').")
    return boe.buscar_articulo(norma, articulo)


async def abrir(c: Cita, seccion: str = "todo", palabras_clave: str = "",
                max_chars: int = 30000) -> str:
    """Lee la cita con la tool adecuada. Las fuentes sincronas van a un hilo."""
    run = asyncio.to_thread
    if c.tipo == "articulo":
        return await run(_articulo, c.norma, c.articulo)
    if c.tipo == "tc":
        return await run(tc.leer_tc, c.ref, seccion=seccion, palabras_clave=palabras_clave,
                         max_chars=max_chars)
    if c.tipo == "tjue":
        sec = seccion if seccion in ("todo", "fallo") else "todo"
        return await run(tjue.leer_tjue, c.ref, seccion=sec, palabras_clave=palabras_clave,
                         max_chars=max_chars)
    if c.tipo == "cendoj":
        return await cendoj_live.leer_sentencia(
            roj=c.extra.get("roj", ""), ecli=c.extra.get("ecli", ""), seccion=seccion,
            palabras_clave=palabras_clave, max_chars=max_chars)
    if c.tipo == "id_cendoj":
        return await run(cendoj.analizar_cita, c.ref)
    if c.tipo == "boe":
        return await run(boe.leer_boe, c.ref)
    if c.tipo == "norma":
        ident = await run(boe.resolver_norma, c.norma)
        if not ident:
            return f"No localizo «{c.norma}» en la legislacion consolidada estatal del BOE."
        return await run(boe.leer_boe, ident)
    if c.tipo == "norma_ue":
        return await run(normativa_ue.articulo_ue, c.ref, "")
    if c.tipo == "dgt":
        return await run(dgt.leer_consulta_hacienda, c.ref)
    if c.tipo == "teac":
        return await run(teac.leer_resolucion_teac, c.ref)
    return f"No se como abrir una cita de tipo «{c.tipo}»."


async def buscar_por_cita(cita: str, seccion: str = "todo", palabras_clave: str = "",
                          max_chars: int = 30000) -> str:
    c = _citas.clasificar(cita)
    if c is None:
        return (
            f"No reconozco «{cita}» como cita. Formatos: STC 31/2010 · STS 1177/2014 · "
            "SAP VA 863/2026 · ECLI:ES:TS:2014:4786 · C-311/18 · ECLI:EU:C:2020:559 · "
            "62018CJ0311 · art. 1902 CC · artículo 46 de la Ley 29/1998 · art. 17 RGPD · "
            "Ley 29/1998 · Directiva 93/13/CEE · BOE-A-2000-323 · V0282-26 (DGT) · "
            "00/06291/2024 (TEAC). Para buscar por tema usa buscar_sentencias / buscar_boe."
        )
    destino = {
        "articulo": "BOE consolidado" if not _citas.es_norma_ue(c.norma) else "CELLAR (UE)",
        "tc": "Tribunal Constitucional", "tjue": "TJUE (CELLAR)", "cendoj": "CENDOJ",
        "id_cendoj": "CENDOJ (Id interno)", "boe": "BOE", "norma": "BOE consolidado",
        "norma_ue": "CELLAR (UE)", "dgt": "DGT", "teac": "TEAC/DYCTEA",
    }[c.tipo]
    salida = await abrir(c, seccion=seccion, palabras_clave=palabras_clave, max_chars=max_chars)
    return f"[Cita «{cita}» → {destino}]\n\n{salida}"


# ---------------------------------------------------------------------------
# Verificar un escrito
# ---------------------------------------------------------------------------

_EXT_TEXTO = (".txt", ".md")


def _leer_fichero(ruta: str) -> str:
    from common.texto import ruta_permitida

    ruta = ruta_permitida(ruta)
    ext = os.path.splitext(ruta)[1].lower()
    if os.path.getsize(ruta) > 50 * 1024 * 1024:
        raise ValueError("fichero demasiado grande (mas de 50 MB)")
    if ext in _EXT_TEXTO:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        import pymupdf

        with pymupdf.open(ruta) as doc:
            return "\n".join(p.get_text() for p in doc)
    if ext == ".docx":
        import zipfile
        from xml.etree import ElementTree as ET

        with zipfile.ZipFile(ruta) as z:
            xml = z.read("word/document.xml")
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        parrafos = []
        for p in ET.fromstring(xml).iter(f"{ns}p"):
            parrafos.append("".join(t.text or "" for t in p.iter(f"{ns}t")))
        return "\n".join(parrafos)
    raise ValueError(f"Formato no soportado: {ext or '(sin extension)'} (usa .txt, .md, .pdf o .docx)")


def _extracto(salida: str, n: int) -> str:
    cuerpo = salida.strip()
    return cuerpo if len(cuerpo) <= n else cuerpo[:n].rsplit(" ", 1)[0] + " […]"


async def _verificar_una(c: Cita, en_linea: bool, incluir_texto: bool) -> dict:
    res = {"cita": c, "estado": "", "detalle": "", "texto": ""}
    if c.tipo == "articulo" and not c.norma:
        res["estado"] = "⚠ SIN NORMA"
        res["detalle"] = "El escrito cita el artículo sin decir de qué norma (o no la reconozco)."
        return res
    if c.tipo == "id_cendoj":
        res["estado"] = "ℹ ID INTERNO"
        res["detalle"] = "Identificador interno del CENDOJ; en un escrito se cita por ROJ/ECLI."
        return res
    if c.tipo == "cendoj" and not en_linea:
        res["estado"] = "… SIN COMPROBAR"
        res["detalle"] = ("Formato valido. No se ha consultado el CENDOJ (navegador, 10-30 s por "
                          "cita): pasa comprobar_cendoj=True o usa buscar_por_cita.")
        return res
    try:
        salida = await abrir(c, seccion="fallo" if c.tipo in ("tc", "tjue", "cendoj") else "todo",
                             max_chars=6000)
    except Exception as e:  # noqa: BLE001
        res["estado"] = "⚠ ERROR DE CONSULTA"
        res["detalle"] = f"{type(e).__name__}: {e}"
        return res
    if _fallo(salida):
        res["estado"] = "✗ NO ENCONTRADA"
        res["detalle"] = _extracto(salida, 300)
        return res
    if c.tipo == "articulo" and _DEROGADO.search(salida):
        res["estado"] = "✗ DEROGADO / SIN CONTENIDO"
    else:
        res["estado"] = "✓ EXISTE"
    m = re.search(r"vigente desde (\S+)", salida)
    m2 = re.search(r"redaccion vigente dada por (\S+)", salida)
    if m or m2:
        res["detalle"] = " · ".join(x for x in (
            f"vigente desde {m.group(1)}" if m else "",
            f"redacción dada por {m2.group(1)} (contrasta con la reforma que cite el escrito)" if m2 else "",
        ) if x)
    if c.tipo == "cendoj" and re.match(r"^[SA]TS\b|^[SA]AP\b|^[SA]TSJ\b", c.ref):
        res["detalle"] = (res["detalle"] + " · " if res["detalle"] else "") + (
            "OJO: se ha interpretado como ROJ; muchos escritos citan el numero de "
            "resolucion, que no coincide con el ROJ. Comprueba fecha y organo.")
    res["texto"] = salida if incluir_texto else _extracto(salida, 900)
    return res


async def verificar_escrito(texto: str = "", ruta: str = "", comprobar_cendoj: bool = False,
                            max_cendoj: int = 3, incluir_texto: bool = False) -> str:
    if ruta and not texto:
        try:
            texto = await asyncio.to_thread(_leer_fichero, ruta)
        except Exception as e:  # noqa: BLE001
            return f"No pude leer «{ruta}»: {e}"
    if not texto.strip():
        return "Pega el texto del escrito en `texto` o indica su `ruta` (.docx, .pdf, .md, .txt)."

    lista = _citas.extraer_citas(texto)
    if not lista:
        return ("No he encontrado citas reconocibles (artículos con su norma, STS/STC/ROJ, ECLI, "
                "asuntos C-/T-, BOE-A, consultas DGT, RG del TEAC).")

    # Las consultas a fuentes rapidas van en paralelo (con tope); el CENDOJ,
    # que abre navegador, de una en una y solo hasta max_cendoj.
    sem = asyncio.Semaphore(4)
    n_cendoj = 0

    async def una(c: Cita) -> dict:
        nonlocal n_cendoj
        if c.tipo == "cendoj":
            en_linea = comprobar_cendoj and n_cendoj < max_cendoj
            if en_linea:
                n_cendoj += 1
            async with _CENDOJ_LOCK:
                return await _verificar_una(c, en_linea, incluir_texto)
        async with sem:
            return await _verificar_una(c, True, incluir_texto)

    resultados = await asyncio.gather(*(una(c) for c in lista))

    malos = [r for r in resultados if r["estado"].startswith(("✗", "⚠"))]
    out = [
        f"VERIFICACION DE CITAS — {len(resultados)} citas · {len(malos)} con incidencias",
        "",
        "Leyenda: ✓ existe (comprueba que el contenido casa con lo que afirma el escrito) · "
        "✗ no encontrada o derogada · ⚠ revisar · … no comprobada.",
        "",
    ]
    if malos:
        out.append("INCIDENCIAS:")
        for r in malos:
            out.append(f"  {r['estado']}  {r['cita'].ref}")
        out.append("")
    for i, r in enumerate(resultados, 1):
        c: Cita = r["cita"]
        out.append(f"── [{i}] {r['estado']}  {c.ref}  ({c.tipo})")
        if c.contexto:
            out.append(f"   El escrito dice: «{c.contexto}»")
        if r["detalle"]:
            out.append(f"   {r['detalle']}")
        if r["texto"]:
            out.append("   Fuente:\n" + "\n".join("     " + l for l in r["texto"].splitlines()))
        out.append("")
    out.append("Siguiente paso: para cada ✓ compara lo que afirma el escrito con el texto "
               "oficial; las citas jurisprudenciales se leen enteras con buscar_por_cita.")
    from common.lecturas import recortar

    return recortar("\n".join(out), 60000, titulo="Verificacion de escrito")


_CENDOJ_LOCK = asyncio.Lock()
