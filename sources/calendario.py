"""Calendario laboral y computo de plazos.

Fuente: la Resolucion anual de la Direccion General de Trabajo «por la que se
publica la relacion de fiestas laborales», que el BOE publica en octubre o
noviembre del ano anterior. La tool la localiza recorriendo los sumarios
oficiales (API de datos abiertos del BOE) y parsea la tabla real del documento.

LIMITE IMPORTANTE: esa Resolucion recoge las fiestas NACIONALES y las de cada
COMUNIDAD AUTONOMA. Las dos fiestas LOCALES de cada municipio no estan ahi: las
publica cada ano el boletin autonomico correspondiente. Por eso el computo de
plazos avisa siempre de que hay que anadirlas a mano si el plazo cae en un
municipio concreto.
"""

from __future__ import annotations

import datetime as dt
import re

from selectolax.parser import HTMLParser

from common.http import get, get_json

API = "https://www.boe.es/datosabiertos/api"
BOE_TXT = "https://www.boe.es/diario_boe/txt.php?id={id}"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}

# Cache por anio: (id_boe, nombres_ccaa, fiestas). Localizar la Resolucion exige
# recorrer sumarios del BOE dia a dia, asi que se hace una sola vez por sesion.
_cache: dict[int, tuple[str, list[str], list[tuple[int, str, list[str]]]]] = {}


def _norm(t: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _fecha(f: str) -> dt.date | None:
    f = (f or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(f, fmt).date()
        except ValueError:
            continue
    return None


def _localizar_resolucion(anio: int) -> tuple[str, str] | None:
    """Busca en los sumarios del BOE la Resolucion de fiestas laborales del anio."""
    for mes, dias in ((10, 31), (11, 30), (12, 31), (9, 30)):
        y = anio - 1
        for d in range(1, dias + 1):
            fecha = dt.date(y, mes, d)
            if fecha.weekday() == 6:
                continue
            try:
                j = get_json(f"{API}/boe/sumario/{fecha:%Y%m%d}")
            except Exception:  # noqa: BLE001
                continue
            hit: list[tuple[str, str]] = []

            def walk(o):
                if isinstance(o, dict):
                    t, i = o.get("titulo"), o.get("identificador")
                    if (isinstance(t, str) and isinstance(i, str)
                            and "fiestas laborales" in t.lower()
                            and str(anio) in t):
                        hit.append((i, t))
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(j)
            if hit:
                return hit[0]
    return None


def _parsear(html: str, anio: int) -> tuple[list[str], list[tuple[int, str, list[str]]]]:
    """Devuelve (nombres_ccaa, [(dia, nombre_fiesta, marcas_por_ccaa)])."""
    tabla = HTMLParser(html).css_first("table")
    if tabla is None:
        return [], []
    filas = tabla.css("tr")
    if len(filas) < 3:
        return [], []
    ccaa = [c.text(strip=True) for c in filas[1].css("th,td")]
    fiestas: list[tuple[int, str, list[str]]] = []
    mes = None
    for fila in filas[2:]:
        celdas = [c.text(strip=True) for c in fila.css("th,td")]
        if not celdas:
            continue
        etiqueta = celdas[0]
        clave = _norm(etiqueta)
        if clave in MESES:
            mes = MESES[clave]
            continue
        m = re.match(r"^(\d{1,2})\s+(.*)$", etiqueta)
        if not m or mes is None:
            continue
        try:
            fecha = dt.date(anio, mes, int(m.group(1)))
        except ValueError:
            continue
        fiestas.append((fecha.toordinal(), m.group(2).strip(), celdas[1:]))
    return ccaa, fiestas


def festivos(anio: int, comunidad: str = "") -> list[tuple[dt.date, str, str]]:
    """Lista de (fecha, nombre, marca) para una CCAA. Sin comunidad, solo nacionales."""
    if anio in _cache:
        bid, ccaa, fiestas = _cache[anio]
    else:
        ref = _localizar_resolucion(anio)
        if ref is None:
            raise LookupError(
                f"No localice en el BOE la Resolucion de fiestas laborales para {anio}."
            )
        bid, _ = ref
        html = get(BOE_TXT.format(id=bid), accept="text/html").text
        ccaa, fiestas = _parsear(html, anio)
        if not ccaa:
            raise LookupError(f"No pude parsear la tabla de {bid}.")
        _cache[anio] = (bid, ccaa, fiestas)

    idx = None
    if comunidad:
        objetivo = _norm(comunidad)
        for i, n in enumerate(ccaa):
            nn = _norm(n)
            if objetivo in nn or nn.split("(")[0].strip() in objetivo:
                idx = i
                break
        if idx is None:
            raise LookupError(
                f"No reconozco la comunidad «{comunidad}». Opciones: {', '.join(ccaa)}"
            )

    out: list[tuple[dt.date, str, str]] = []
    for orden, nombre, marcas in fiestas:
        fecha = dt.date.fromordinal(orden)
        if idx is None:
            if marcas and all(m.strip() for m in marcas):
                out.append((fecha, nombre, "nacional"))
        elif idx < len(marcas) and marcas[idx].strip():
            out.append((fecha, nombre, marcas[idx].strip()))
    return out


def calendario_laboral(anio: int, comunidad: str = "") -> str:
    """Fiestas laborales de un ano (nacionales y de la CCAA indicada)."""
    try:
        lista = festivos(anio, comunidad)
    except LookupError as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return f"Error consultando el calendario laboral de {anio}: {e}"

    dias = "LMXJVSD"
    cab = f"FIESTAS LABORALES {anio}"
    cab += f" — {comunidad}" if comunidad else " — nacionales"
    filas = [
        f"  {f:%d/%m/%Y} ({dias[f.weekday()]})  {n}" for f, n, _ in lista
    ]
    return (
        f"{cab}  ({len(lista)} dias)\n\n" + "\n".join(filas) + "\n\n"
        "Fuente: Resolucion anual de la Direccion General de Trabajo (BOE).\n"
        "AVISO: no incluye las DOS FIESTAS LOCALES de cada municipio, que publica "
        "el boletin autonomico. Comprueba las del municipio que corresponda antes "
        "de computar un plazo."
    )


def computo_plazo(
    desde: str,
    dias: int,
    comunidad: str = "",
    festivos_locales: str = "",
    naturales: bool = False,
) -> str:
    """Computa el vencimiento de un plazo en dias habiles (o naturales).

    `desde` es el dia inicial del computo (dies a quo ya determinado por quien
    llama). En dias habiles se excluyen sabados, domingos y festivos.
    """
    ini = _fecha(desde)
    if ini is None:
        return "Fecha invalida. Usa dd/mm/aaaa."
    if dias < 1:
        return "El numero de dias debe ser positivo."

    extra: set[dt.date] = set()
    for tok in re.split(r"[;,]", festivos_locales or ""):
        f = _fecha(tok)
        if f:
            extra.add(f)

    inhabiles: dict[dt.date, str] = {}
    fallidos: dict[int, str] = {}
    cargados: set[int] = set()

    def cargar(anio: int) -> None:
        """Carga los festivos de un anio solo cuando el computo llega a el."""
        if anio in cargados or anio in fallidos:
            return
        try:
            for f, n, _ in festivos(anio, comunidad):
                inhabiles[f] = n
            cargados.add(anio)
        except Exception as e:  # noqa: BLE001
            fallidos[anio] = str(e)

    if not naturales:
        cargar(ini.year)
        for f in extra:
            inhabiles[f] = "festivo local (indicado)"

    contados = 0
    d = ini
    detalle: list[str] = []
    while True:
        salta = None
        if not naturales:
            cargar(d.year)  # solo se piden los anios que el computo realmente cruza
            if d.weekday() >= 5:
                salta = "fin de semana"
            elif d in inhabiles:
                salta = inhabiles[d]
        if salta:
            detalle.append(f"  {d:%d/%m/%Y} — no computa ({salta})")
        else:
            contados += 1
            if contados in (1, dias):
                detalle.append(f"  {d:%d/%m/%Y} — dia {contados}")
            if contados >= dias:
                break
        d += dt.timedelta(days=1)
        if (d - ini).days > 2000:
            return "Computo abortado: rango excesivo."

    tipo = "naturales" if naturales else "habiles"
    saltados = [l for l in detalle if "no computa" in l]
    return (
        f"COMPUTO DE PLAZO — {dias} dias {tipo}\n"
        f"Dia inicial : {ini:%d/%m/%Y}\n"
        f"VENCIMIENTO : {d:%d/%m/%Y} ({['lunes','martes','miercoles','jueves','viernes','sabado','domingo'][d.weekday()]})\n"
        + (f"\nDias excluidos ({len(saltados)}):\n" + "\n".join(saltados) if saltados else "")
        + (f"\n\nFestivos aplicados: {comunidad or 'solo nacionales'}"
           + (f" + {len(extra)} local(es) indicado(s)" if extra else "")
           if not naturales else "")
        + ("\nAVISO: las dos fiestas LOCALES del municipio no estan en la Resolucion "
           "estatal. Si alguna cae en el periodo y no la has indicado, el vencimiento "
           "se desplaza." if not naturales and not extra else "")
        + ("\nAVISO: no pude cargar los festivos oficiales de "
           + ", ".join(str(a) for a in sorted(fallidos))
           + ", anio(s) que el computo atraviesa; en ese tramo solo se han excluido "
             "fines de semana. Verifica el vencimiento."
           if fallidos else "")
    )
