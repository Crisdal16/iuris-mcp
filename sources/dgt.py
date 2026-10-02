"""DGT — doctrina de la Direccion General de Tributos (consultas de Hacienda).

Fuente: buscador oficial PETETE de la Secretaria de Estado de Hacienda
  https://petete.tributos.hacienda.gob.es/consultas/

VIABILIDAD (verificada con peticiones reales, sin evadir nada):
  - robots.txt: vacio (sin restricciones). Sin captcha ni login.
  - El buscador es una interfaz KNOSYS que responde por AJAX a dos rutas GET:
      /consultas/do/search    -> fragmento HTML con la lista de resultados
      /consultas/do/document  -> fragmento HTML con el documento completo
    Ambas exigen la cabecera 'X-Requested-With: XMLHttpRequest' (si falta, el
    documento devuelve 401). El listado marca cada resultado con un id interno
    ('doc_74271') que hay que reutilizar para abrir el documento; por eso
    'leer_consulta_hacienda' busca primero por numero para descubrir ese id.

  - IMPORTANTE (por que NO se usa common.http aqui): el servidor de PETETE
    presenta una cadena TLS incompleta (no envia el certificado intermedio de la
    FNMT), de modo que la verificacion estandar falla con CERTIFICATE_VERIFY_
    FAILED. La solucion NO es desactivar la verificacion: se COMPLETA la cadena
    anadiendo el intermedio oficial de la FNMT (guardado en common/certs/) a los
    certificados de confianza, de modo que la verificacion TLS sigue siendo real
    (ver _bundle_ca). Ademas common.http no permite fijar la cabecera XHR que el
    buscador exige. Por esas dos razones este modulo usa un cliente httpx propio.

Todas las funciones devuelven texto legible en espanol. Si algo falla, se
entrega la URL oficial del buscador para que la persona la abra a mano.
"""

from __future__ import annotations

import os
import re
import ssl

import httpx
from selectolax.parser import HTMLParser

from common.http import describir_error
from common.lecturas import recortar
from common.texto import parrafos

BASE = "https://petete.tributos.hacienda.gob.es/consultas"
BUSCADOR_URL = BASE + "/"

# tab del buscador -> coleccion de consultas
_TAB_VINCULANTES = "2"
_TAB_GENERALES = "1"

_USER_AGENT = "iuris-mcp/0.1 (servidor MCP juridico de uso profesional propio)"
_TIMEOUT = 90.0
_XHR = {
    "User-Agent": _USER_AGENT,
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BUSCADOR_URL,
}

_RE_FECHA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RE_FECHA_ES = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_RE_NUM = re.compile(r"^[VG]?\d{3,5}-\d{2}$", re.IGNORECASE)


def _bundle_ca() -> str:
    """CA bundle = certifi + el certificado intermedio de la FNMT que PETETE omite.

    El servidor de PETETE presenta la cadena TLS INCOMPLETA (envia solo el
    certificado de servidor, sin el intermedio 'AC Componentes Informaticos' de
    la FNMT-RCM). En vez de desactivar la verificacion (verify=False, inseguro),
    completamos la cadena anadiendo ese intermedio —descargado de la FNMT y
    guardado en el repo— a los certificados de confianza de certifi. Asi la
    verificacion TLS es REAL: se valida el servidor contra la raiz oficial FNMT.
    """
    import certifi

    intermedio = os.path.join(os.path.dirname(__file__), "..", "common", "certs",
                              "fnmt_accomp_intermediate.pem")
    intermedio = os.path.abspath(intermedio)
    combinado = certifi.contents() + "\n" + open(intermedio, encoding="ascii").read()
    ctx = ssl.create_default_context(cadata=combinado)
    return ctx


def _cliente() -> httpx.Client:
    """Cliente con sesion (JSESSIONID), cabecera XHR y verificacion TLS REAL.

    La cadena TLS de PETETE llega incompleta; se completa con el intermedio de la
    FNMT (ver _bundle_ca). El buscador exige la cabecera X-Requested-With, que
    common.http no permite fijar; de ahi el cliente propio.
    """
    return httpx.Client(headers=_XHR, timeout=_TIMEOUT, follow_redirects=True,
                        verify=_bundle_ca())


def _abrir_sesion(c: httpx.Client) -> None:
    """Primera peticion para obtener la cookie de sesion (JSESSIONID)."""
    try:
        c.get(BUSCADOR_URL)
    except httpx.HTTPError:
        pass


def _fecha_es(f: str) -> str:
    """Normaliza una fecha a dd/mm/aaaa (formato que espera el buscador)."""
    f = (f or "").strip()
    if not f:
        return ""
    m = _RE_FECHA_ISO.match(f)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = _RE_FECHA_ES.match(f)
    if m:
        return f
    return ""


def _params_busqueda(consulta: str, numero: str, normativa: str,
                     desde: str, hasta: str, tab: str, page: int) -> dict:
    """Construye SOLO los campos no vacios (los vacios cuelgan el motor KNOSYS)."""
    p: dict[str, str] = {}
    n = 0
    if numero.strip():
        p.update({"NMCMP_1": "NUM-CONSULTA", "VLCMP_1": numero.strip(),
                  "OPCMP_1": ".Y"})
        n += 1
    di = _fecha_es(desde)
    dh = _fecha_es(hasta)
    if di or dh:
        p.update({"NMCMP_2": "FECHA-SALIDA", "OPCMP_2": ".Y",
                  "dateIni_2": di, "dateEnd_2": dh})
        n += 1
    if normativa.strip():
        p.update({"NMCMP_3": "NORMATIVA", "VLCMP_3": normativa.strip(),
                  "OPCMP_3": ".Y"})
        n += 1
    if consulta.strip():
        p.update({"NMCMP_6": "FreeText", "VLCMP_6": consulta.strip(),
                  "OPCMP_6": ".Y"})
        n += 1
    p["tab"] = tab
    p["page"] = str(page)
    return p


def _extraer_total(fragmento: str) -> int | None:
    """Numero total de resultados que anuncia el propio fragmento (KNOSYS)."""
    m = re.search(r'updateNumResults\(\s*"?\d+"?\s*,\s*"?(\d+)"?\s*\)', fragmento)
    return int(m.group(1)) if m else None


def _parsear_resultados(fragmento: str) -> list[dict]:
    """De un fragmento /do/search a una lista de dicts (num, doc, tab, hechos...)."""
    doc = HTMLParser(fragmento)
    filas: list[dict] = []
    for td in doc.css("td[id]"):
        if not (td.attributes.get("id") or "").startswith("doc_"):
            continue
        oc = td.attributes.get("onclick") or td.attributes.get("onClick") or ""
        m = re.search(r"viewDocument\((\d+),\s*(\d+)\)", oc)
        if not m:
            continue
        num_node = td.css_first(".NUM-CONSULTA")
        hechos = td.css_first(".DESCRIPCION-HECHOS")
        cuestion = td.css_first(".CUESTION-PLANTEADA")
        filas.append({
            "numero": (num_node.text() if num_node else "").strip(),
            "doc": m.group(1),
            "tab": m.group(2),
            "hechos": " ".join((hechos.text() if hechos else "").split()),
            "cuestion": " ".join((cuestion.text() if cuestion else "").split()),
        })
    return filas


def _tabs_por_tipo(tipo: str) -> list[tuple[str, str]]:
    t = (tipo or "").strip().lower()
    if t in ("generales", "general"):
        return [(_TAB_GENERALES, "Generales")]
    if t in ("ambas", "todas", "todos", "ambos", ""):
        return [(_TAB_VINCULANTES, "Vinculantes"), (_TAB_GENERALES, "Generales")]
    return [(_TAB_VINCULANTES, "Vinculantes")]


def buscar_consultas_hacienda(consulta: str = "", numero: str = "",
                              normativa: str = "", desde: str = "",
                              hasta: str = "", tipo: str = "vinculantes",
                              limite: int = 15) -> str:
    """Busca consultas de la DGT (doctrina de Hacienda) en el buscador oficial.

    Parametros (todos opcionales, se combinan con Y):
      consulta  -> texto libre (busca en todo el documento).
      numero    -> nº de consulta, p.ej. 'V0282-26'.
      normativa -> articulo/ley citada, p.ej. 'Ley 37/1992'.
      desde/hasta -> fecha de salida (aaaa-mm-dd o dd/mm/aaaa).
      tipo      -> 'vinculantes' (def.), 'generales' o 'ambas'.
      limite    -> maximo de resultados a mostrar por tipo.
    """
    if not any([consulta.strip(), numero.strip(), normativa.strip(),
                desde.strip(), hasta.strip()]):
        return ("Indica al menos un criterio (consulta, numero, normativa o "
                "fechas).\nBuscador oficial DGT: " + BUSCADOR_URL)

    limite = max(1, min(int(limite or 15), 50))
    partes: list[str] = []
    cab = "Consultas DGT (Hacienda)"
    filtros = []
    if consulta.strip():
        filtros.append(f'texto "{consulta.strip()}"')
    if numero.strip():
        filtros.append(f"numero {numero.strip()}")
    if normativa.strip():
        filtros.append(f"normativa {normativa.strip()}")
    if desde.strip() or hasta.strip():
        filtros.append(f"fecha {desde.strip() or '...'}-{hasta.strip() or '...'}")
    partes.append(f"{cab} — {'; '.join(filtros)}")

    try:
        with _cliente() as c:
            _abrir_sesion(c)
            for tab, etiqueta in _tabs_por_tipo(tipo):
                r = c.get(BASE + "/do/search",
                          params=_params_busqueda(consulta, numero, normativa,
                                                   desde, hasta, tab, 1))
                r.raise_for_status()
                total = _extraer_total(r.text)
                filas = _parsear_resultados(r.text)
                partes.append("")
                if not filas:
                    partes.append(f"[{etiqueta}] Sin resultados.")
                    continue
                enc = f"[{etiqueta}] {total if total is not None else len(filas)} resultados"
                if total and total > len(filas):
                    enc += f" (se muestran {min(limite, len(filas))} de esta pagina)"
                partes.append(enc)
                for f in filas[:limite]:
                    linea = f"\n  · {f['numero']}"
                    if f["cuestion"]:
                        linea += f"\n      Cuestion: {f['cuestion'][:280]}"
                    elif f["hechos"]:
                        linea += f"\n      Hechos: {f['hechos'][:280]}"
                    partes.append(linea)
    except httpx.HTTPError as e:
        return (f"No se pudo consultar el buscador de la DGT ({describir_error(e)}).\n"
                f"Abrelo a mano: {BUSCADOR_URL}")

    partes.append(f"\nPara el texto integro: leer_consulta_hacienda('Vxxxx-xx').\n"
                  f"Buscador oficial: {BUSCADOR_URL}")
    return "\n".join(partes)


def _localizar_doc(c: httpx.Client, numero: str) -> tuple[str, str] | None:
    """Busca por NUM-CONSULTA en ambas colecciones y devuelve (doc_id, tab)."""
    for tab in (_TAB_VINCULANTES, _TAB_GENERALES):
        r = c.get(BASE + "/do/search",
                  params=_params_busqueda("", numero, "", "", "", tab, 1))
        r.raise_for_status()
        filas = _parsear_resultados(r.text)
        for f in filas:
            if f["numero"].replace(" ", "").upper() == numero.replace(" ", "").upper():
                return f["doc"], f["tab"]
        if filas:  # coincidencia unica aunque el texto varie
            return filas[0]["doc"], filas[0]["tab"]
    return None


def leer_consulta_hacienda(numero: str, max_chars: int = 30000) -> str:
    """Texto integro de una consulta de la DGT por su numero (p.ej. 'V0282-26')."""
    numero = (numero or "").strip()
    if not numero:
        return "Indica el numero de consulta (p.ej. 'V0282-26')."
    if not _RE_NUM.match(numero):
        return (f"'{numero}' no parece un numero de consulta valido "
                f"(formato tipo 'V0282-26').")

    try:
        with _cliente() as c:
            _abrir_sesion(c)
            loc = _localizar_doc(c, numero)
            if not loc:
                return (f"No encuentro la consulta {numero} en el buscador de la DGT.\n"
                        f"Compruebala a mano: {BUSCADOR_URL}")
            doc, tab = loc
            r = c.get(BASE + "/do/document", params={"doc": doc, "tab": tab})
            r.raise_for_status()
    except httpx.HTTPError as e:
        return (f"No se pudo leer la consulta {numero} ({describir_error(e)}).\n"
                f"Abrela a mano: {BUSCADOR_URL}")

    doc_html = HTMLParser(r.text)
    campos: list[str] = []
    for tr in doc_html.css("tr[class]"):
        th = tr.css_first("th.field")
        td = tr.css_first("td.value")
        if not th or not td:
            continue
        etiqueta = " ".join(th.text().split())
        # El HTML de PETETE parte las lineas con sangria de 12 espacios: se
        # reagrupan en parrafos.
        lineas = [l.strip() for l in td.text(separator="\n").splitlines() if l.strip()]
        valor = "\n".join(parrafos("\n".join(lineas)))
        valor = re.sub(r"\n{3,}", "\n\n", valor).strip()
        if etiqueta and valor:
            campos.append(f"{etiqueta}:\n{valor}" if len(valor) > 80
                          else f"{etiqueta}: {valor}")
    if not campos:
        return (f"La consulta {numero} no devolvio contenido legible.\n"
                f"Abrela a mano: {BUSCADOR_URL}")
    cabecera = "Direccion General de Tributos — Consulta " + numero
    return recortar(cabecera + "\n\n" + "\n\n".join(campos), max_chars,
                    titulo=f"Consulta DGT {numero}")
