"""CENDOJ en vivo — busqueda y descarga real de jurisprudencia.

A diferencia de `sources/cendoj.py` (que solo prepara la URL para que la abra el
usuario), este modulo SI accede al buscador del CENDOJ y trae los resultados y el
texto de las resoluciones.

USO PREVISTO (importante): consulta profesional propia, documento a documento y
bajo demanda. NO es una herramienta de descarga masiva ni para construir una base
de datos derivada (eso lo prohibe el aviso legal del CENDOJ). Cada llamada trae
una pagina de resultados o una resolucion concreta.

Diseno tecnico, validado contra el sitio real (sept. 2026):

  BUSQUEDA (necesita navegador — Playwright/Chromium):
  • Formulario: https://www.poderjudicial.es/search/indexAN.jsp
  • Se teclea la consulta caracter a caracter y se elige una sugerencia del
    autocompletado (ul.ui-autocomplete). Es como el sitio espera que se use su
    buscador y evita el aviso "Control de grandes paginaciones".
  • Un navegador nuevo por llamada: sesion limpia, sin estado acumulado.

  LECTURA (NO necesita navegador):
  • La URL de la ficha (.../openDocument/<ref>/<optimize>) contiene todo lo
    necesario para construir el enlace directo del PDF (contenidos.action?
    action=accessToPDF&reference=<ref>&optimize=<optimize>...). Se descarga con
    httpx en ~1-2 s. Texto extraido con PyMuPDF.
  • El CENDOJ limita a ~6-7 descargas por sesion; como cada descarga va sin
    sesion previa, no se acumula. Aun asi: documento a documento.
  • Cache (diskcache) de bytes y texto por referencia: la 2a lectura es
    instantanea y no vuelve a tocar el CENDOJ.

  Fallback: si el enlace directo no devuelve un PDF (cambio del sitio), se
  resuelve la ficha con el navegador y se reintenta con sus cookies.
"""

from __future__ import annotations

import os
import re
from typing import Any

from common.cendoj_ids import Ecli, Roj, normalizar_cita, roj_a_ecli
from common.texto import dir_destino, norm as _norm, parrafos, parrafos_con, slug as _slug, truncar

BASE_FORM = "https://www.poderjudicial.es/search/indexAN.jsp"
SITE = "https://www.poderjudicial.es"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-ES,es;q=0.9"}

# .../search/AN/openDocument/<reference 32 hex>/<optimize 8 digitos>
_RE_FICHA = re.compile(r"openDocument/(?P<ref>[0-9a-f]{32})/(?P<opt>\d{8})", re.IGNORECASE)
_PDF_DIRECTO = (SITE + "/search/contenidos.action?action=accessToPDF&publicinterface=true"
                "&tab=AN&databasematch=AN&reference={ref}&encode=true&optimize={opt}")

# --- Cache (diskcache, ya es dependencia del proyecto) -----------------------
try:
    from diskcache import Cache

    _CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "cendoj")
    _cache: Any = Cache(_CACHE_DIR, size_limit=int(2e9))
except Exception:  # pragma: no cover
    _cache = None


def _cache_get(clave: str):
    try:
        return _cache.get(clave) if _cache is not None else None
    except Exception:
        return None


def _cache_set(clave: str, valor) -> None:
    try:
        if _cache is not None and valor:
            _cache.set(clave, valor)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Normalizacion de filtros a las etiquetas exactas del formulario
# ---------------------------------------------------------------------------

_JURISDICCION_LABEL = {
    "CIVIL": "Civil",
    "PENAL": "Penal",
    "CONTENCIOSO": "Contencioso-Administrativo",
    "CONTENCIOSO-ADMINISTRATIVO": "Contencioso-Administrativo",
    "CONTENCIOSO ADMINISTRATIVO": "Contencioso-Administrativo",
    "SOCIAL": "Social",
    "LABORAL": "Social",
    "MILITAR": "Militar",
}

# Provincia -> Comunidad Autonoma (el filtro "Localizacion" del CENDOJ va por CCAA)
_PROVINCIA_A_CCAA = {
    "ALAVA": "País Vasco", "ARABA": "País Vasco", "GIPUZKOA": "País Vasco",
    "GUIPUZCOA": "País Vasco", "BIZKAIA": "País Vasco", "VIZCAYA": "País Vasco",
    "BILBAO": "País Vasco", "SAN SEBASTIAN": "País Vasco",
    "BARCELONA": "Cataluña", "GIRONA": "Cataluña", "GERONA": "Cataluña",
    "LLEIDA": "Cataluña", "LERIDA": "Cataluña", "TARRAGONA": "Cataluña",
    "MADRID": "Madrid",
    "MURCIA": "Murcia", "CARTAGENA": "Murcia", "LORCA": "Murcia",
    "VALENCIA": "Comunidad Valenciana", "ALICANTE": "Comunidad Valenciana",
    "ALACANT": "Comunidad Valenciana", "CASTELLON": "Comunidad Valenciana",
    "SEVILLA": "Andalucía", "MALAGA": "Andalucía", "CADIZ": "Andalucía",
    "GRANADA": "Andalucía", "CORDOBA": "Andalucía", "ALMERIA": "Andalucía",
    "JAEN": "Andalucía", "HUELVA": "Andalucía",
    "ZARAGOZA": "Aragón", "HUESCA": "Aragón", "TERUEL": "Aragón",
    "ASTURIAS": "Asturias", "OVIEDO": "Asturias",
    "BALEARES": "Islas Baleares", "ILLES BALEARS": "Islas Baleares", "PALMA": "Islas Baleares",
    "LAS PALMAS": "Canarias", "PALMAS": "Canarias",
    "SANTA CRUZ DE TENERIFE": "Canarias", "TENERIFE": "Canarias",
    "CANTABRIA": "Cantabria", "SANTANDER": "Cantabria",
    "ALBACETE": "Castilla-La Mancha", "CIUDAD REAL": "Castilla-La Mancha",
    "CUENCA": "Castilla-La Mancha", "GUADALAJARA": "Castilla-La Mancha",
    "TOLEDO": "Castilla-La Mancha",
    "AVILA": "Castilla y León", "BURGOS": "Castilla y León", "LEON": "Castilla y León",
    "PALENCIA": "Castilla y León", "SALAMANCA": "Castilla y León",
    "SEGOVIA": "Castilla y León", "SORIA": "Castilla y León",
    "VALLADOLID": "Castilla y León", "ZAMORA": "Castilla y León",
    "BADAJOZ": "Extremadura", "CACERES": "Extremadura",
    "A CORUNA": "Galicia", "LA CORUNA": "Galicia", "CORUNA": "Galicia",
    "LUGO": "Galicia", "OURENSE": "Galicia", "ORENSE": "Galicia",
    "PONTEVEDRA": "Galicia", "VIGO": "Galicia",
    "LA RIOJA": "La Rioja", "RIOJA": "La Rioja", "LOGRONO": "La Rioja",
    "NAVARRA": "Navarra", "PAMPLONA": "Navarra",
    "CEUTA": "Ceuta", "MELILLA": "Melilla",
}


def _label_jurisdiccion(valor: str) -> str | None:
    return _JURISDICCION_LABEL.get(_norm(valor))


def _label_localizacion(valor: str) -> str:
    """Acepta CCAA ('Cataluña') o provincia ('Barcelona') -> etiqueta CCAA del form."""
    n = _norm(valor)
    if n in _PROVINCIA_A_CCAA:
        return _PROVINCIA_A_CCAA[n]
    return valor  # se pasa tal cual (has-text es tolerante)


def _absolutizar(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return (SITE + href) if href.startswith("/") else (SITE + "/search/" + href)


def url_pdf_directa(url_ficha: str) -> str | None:
    """.../openDocument/<ref>/<opt> -> enlace directo accessToPDF. None si no encaja."""
    m = _RE_FICHA.search(url_ficha or "")
    if not m:
        return None
    return _PDF_DIRECTO.format(ref=m.group("ref"), opt=m.group("opt"))


def _clave_doc(url_ficha: str) -> str:
    m = _RE_FICHA.search(url_ficha or "")
    return m.group("ref") if m else url_ficha


def _fecha(s: str) -> str:
    """AAAA-MM-DD -> DD/MM/AAAA. Deja pasar lo ya en DD/MM/AAAA."""
    s = (s or "").strip()
    if "-" in s:
        p = s.split("-")
        if len(p) == 3 and len(p[0]) == 4:
            return f"{p[2]}/{p[1]}/{p[0]}"
    return s


def _m(patron: str, texto: str) -> str | None:
    r = re.search(patron, texto, re.IGNORECASE)
    return " ".join(r.group(1).split()) if r else None


def _meta_desde_texto(texto: str) -> dict:
    """Metadatos desde la cabecera estandar del PDF del CENDOJ."""
    cab = texto[:1500]
    return {
        "roj": _m(r"Roj:\s*([^\n\r-]+?)\s*(?:-|\n)", cab),
        "ecli": _m(r"(ECLI:[A-Z]{2}:[^\s\n\r]+)", cab),
        "id_cendoj": _m(r"Id Cendoj:\s*(\d{20})", cab),
        "organo": _m(r"[ÓO]rgano:\s*([^\n\r]+)", cab),
        "sede": _m(r"Sede:\s*([^\n\r]+)", cab),
        "seccion": _m(r"Secci[óo]n:\s*([^\n\r]+)", cab),
        "fecha": _m(r"Fecha:\s*([0-9/]+)", cab),
        "ponente": _m(r"Ponente:\s*([^\n\r]+)", cab),
        "n_recurso": _m(r"N[ºo]\s*de Recurso:\s*([^\n\r]+)", cab),
        "n_resolucion": _m(r"N[ºo]\s*de Resoluci[óo]n:\s*([^\n\r]+)", cab),
        "procedimiento": _m(r"Procedimiento:\s*([^\n\r]+)", cab),
        "tipo": _m(r"Tipo de Resoluci[óo]n:\s*([^\n\r]+)", cab),
    }


# ---------------------------------------------------------------------------
# Estructura de la resolucion: secciones y parrafos
# ---------------------------------------------------------------------------

# Cabeceras habituales (sentencias y autos), como linea propia y en mayusculas.
_SECCIONES = [
    ("antecedentes", r"ANTECEDENTES\s+DE\s+HECHO"),
    ("hechos", r"HECHOS\s+PROBADOS|HECHOS\s+DECLARADOS\s+PROBADOS"),
    ("fundamentos", r"FUNDAMENTOS\s+(?:DE\s+)?DERECHO|FUNDAMENTOS\s+JUR[ÍI]DICOS|RAZONAMIENTOS\s+JUR[ÍI]DICOS"),
    ("fallo", r"F\s?A\s?L\s?L\s?(?:O|AMOS)|PARTE\s+DISPOSITIVA|LA\s+SALA\s+ACUERDA|ACUERDO|DISPONGO"),
]
_ALIAS_SECCION = {
    "todo": "todo", "completo": "todo", "": "todo",
    "fallo": "fallo", "parte dispositiva": "fallo",
    "fundamentos": "fundamentos", "fundamentos de derecho": "fundamentos", "fd": "fundamentos",
    "antecedentes": "antecedentes", "antecedentes de hecho": "antecedentes",
    "hechos": "hechos", "hechos probados": "hechos",
    "encabezado": "encabezado", "cabecera": "encabezado",
}


def secciones(texto: str) -> dict[str, str]:
    """Parte el texto en encabezado / antecedentes / hechos / fundamentos / fallo.

    Busca cada cabecera como linea propia (tolera espacios y puntuacion final).
    Devuelve solo las secciones encontradas; 'encabezado' es lo previo a la
    primera cabecera. Si no se reconoce ninguna, devuelve {'todo': texto}.
    """
    marcas: list[tuple[int, str]] = []
    for nombre, patron in _SECCIONES:
        rx = re.compile(rf"^[ \t]*(?:{patron})[ \t.:\-]*$", re.MULTILINE | re.IGNORECASE)
        for m in rx.finditer(texto):
            # Solo cabeceras "reales": en mayusculas en el original.
            if m.group(0).strip() == m.group(0).strip().upper():
                marcas.append((m.start(), nombre))
    if not marcas:
        return {"todo": texto}
    marcas.sort()
    # Si una seccion aparece varias veces (p.ej. 'FALLO' citado), nos quedamos
    # con la PRIMERA de cada nombre en orden de aparicion, pero el FALLO se toma
    # la ULTIMA (lo dispositivo cierra la resolucion).
    primeras: dict[str, int] = {}
    for pos, nombre in marcas:
        if nombre == "fallo":
            primeras[nombre] = pos
        else:
            primeras.setdefault(nombre, pos)
    orden = sorted(primeras.items(), key=lambda kv: kv[1])
    out: dict[str, str] = {}
    if orden[0][1] > 0:
        out["encabezado"] = texto[: orden[0][1]].strip()
    for i, (nombre, pos) in enumerate(orden):
        fin = orden[i + 1][1] if i + 1 < len(orden) else len(texto)
        out[nombre] = texto[pos:fin].strip()
    return out


# (parrafos / parrafos_con viven en common.texto y se reexportan desde aqui)


# ---------------------------------------------------------------------------
# Descarga directa (sin navegador)
# ---------------------------------------------------------------------------

async def _descargar_pdf_httpx(url_pdf: str, cookies: dict | None = None) -> bytes | None:
    import httpx

    try:
        async with httpx.AsyncClient(headers=_HEADERS, cookies=cookies or {},
                                     follow_redirects=True, timeout=30.0) as cli:
            r = await cli.get(url_pdf)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            return r.content
    except Exception:
        pass
    return None


def _texto_de_pdf(data: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return "\n".join(p.get_text() for p in doc)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Navegador CENDOJ (context manager async, un navegador por llamada)
# ---------------------------------------------------------------------------

class CendojBrowser:
    def __init__(self, headless: bool | None = None):
        if headless is None:
            headless = os.getenv("CENDOJ_HEADLESS", "true").lower() != "false"
        self.headless = headless
        self._pw = None
        self.browser = None
        self.ctx = None
        self.page = None

    async def __aenter__(self) -> "CendojBrowser":
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Playwright no esta instalado en el entorno del servidor. Instala con: "
                "python -m pip install playwright && python -m playwright install chromium"
            ) from e
        self._pw = await async_playwright().start()
        try:
            self.browser = await self._pw.chromium.launch(
                headless=self.headless, args=["--no-sandbox", "--disable-web-security"]
            )
        except Exception as e:
            await self._pw.stop()
            raise RuntimeError(
                "No se pudo lanzar Chromium. Ejecuta una vez: python -m playwright install chromium"
                f" (detalle: {e})"
            ) from e
        self.ctx = await self.browser.new_context(
            viewport={"width": 1280, "height": 1000}, user_agent=_UA, locale="es-ES"
        )
        self.page = await self.ctx.new_page()
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            if self.browser:
                await self.browser.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def _cerrar_modal(self) -> None:
        try:
            btn = self.page.locator('button.close, button[data-dismiss="modal"]').first
            if await btn.is_visible():
                await btn.click(timeout=2000)
                await self.page.wait_for_timeout(600)
        except Exception:
            pass

    async def buscar(
        self,
        consulta: str = "",
        *,
        jurisdiccion: list[str] | None = None,
        localizacion: list[str] | None = None,
        fecha_desde: str = "",
        fecha_hasta: str = "",
        roj: str = "",
        ecli: str = "",
        ponente: str = "",
        norma: str = "",
        n_recurso: str = "",
        n_resolucion: str = "",
        pagina: int = 1,
        por_pagina: int = 10,
        orden: str = "",
    ) -> dict:
        page = self.page
        await page.goto(BASE_FORM, timeout=30000)
        await page.wait_for_load_state("networkidle")
        await self._cerrar_modal()

        if consulta:
            campo = page.locator("input#frmBusquedajurisprudencia_TEXT")
            await campo.focus()
            await campo.fill("")
            await campo.press_sequentially(consulta, delay=32)
            auto = page.locator("ul.ui-autocomplete li")
            try:
                await auto.first.wait_for(state="visible", timeout=3500)
                await auto.first.click()
                await page.wait_for_timeout(400)
            except Exception:
                pass  # sin autocompletado; seguimos con la query cruda

        campos = {
            "input#frmBusquedajurisprudencia_ROJ": roj,
            "input#frmBusquedajurisprudencia_ECLI": ecli,
            "input#frmBusquedajurisprudencia_NUMERORESOLUCION": n_resolucion,
            "input#frmBusquedajurisprudencia_NUMERORECURSO": n_recurso,
            "input#frmBusquedajurisprudencia_PONENTE": ponente,
            "input#frmBusquedajurisprudencia_NORMA": norma,
            "input#frmBusquedajurisprudencia_FECHARESOLUCIONDESDE": _fecha(fecha_desde),
            "input#frmBusquedajurisprudencia_FECHARESOLUCIONHASTA": _fecha(fecha_hasta),
        }
        for sel, val in campos.items():
            if val:
                try:
                    await page.fill(sel, val)
                except Exception:
                    pass

        if jurisdiccion:
            await self._marcar_multiselect(
                "button#frmBusquedajurisprudencia_JURISDICCIONmultiselec",
                [_label_jurisdiccion(j) or j for j in jurisdiccion],
            )
        if localizacion:
            await self._marcar_multiselect(
                "button#COMUNIDADmultiselec",
                [_label_localizacion(loc) for loc in localizacion],
            )

        await page.click("button#srcjur_search")
        if not await self._esperar_resultados(30000):
            return {"total": 0, "resultados": []}

        if por_pagina > 10:
            await self._resultados_por_pagina(por_pagina)
        if orden:
            await self._ordenar(orden)
        if pagina > 1:
            await self._ir_a_pagina(pagina)

        body_text = await page.inner_text("body")
        m = re.search(r"(\d[\d\.]*)\s+resultados", body_text, re.IGNORECASE)
        total = int(m.group(1).replace(".", "")) if m else None

        resultados = await self._parsear_tarjetas()
        if total is None:
            total = len(resultados)
        return {"total": total, "resultados": resultados}

    async def _esperar_carga(self) -> None:
        try:
            await self.page.wait_for_selector("div.loading-results", state="hidden", timeout=8000)
        except Exception:
            pass

    async def _esperar_resultados(self, timeout: int) -> bool:
        """True si hay tarjetas; False si el sitio dice 'sin resultados'. Lanza si
        no responde (timeout) o si aparece el control anti-bot."""
        try:
            await self.page.wait_for_selector(
                'div#jurisprudenciaresults_searchresults a[id^="ref-"]',
                state="attached", timeout=timeout,
            )
            return True
        except Exception:
            body = (await self.page.inner_text("body")).lower()
            if "no se han encontrado" in body or "sin resultados" in body:
                return False
            if "grandes paginaciones" in body or "captcha" in body:
                raise RuntimeError(
                    "El CENDOJ ha mostrado su control anti-bot. Espera unos minutos y "
                    "reintenta; si persiste, usa cendoj_construir_busqueda y abre el "
                    "enlace en tu navegador."
                )
            raise RuntimeError("El CENDOJ no ha devuelto resultados a tiempo (timeout). "
                               "Reintenta o acota la busqueda.")

    # Los desplegables del listado son widgets bootstrap-select: el <select>
    # nativo esta oculto, asi que select_option() se queda esperando. Se cambia
    # el valor por JS y se dispara 'change' (es lo que hace el propio widget), y
    # luego se espera a que el listado se haya recargado de verdad.

    _JS_PRIMER_ID = ("() => { const a = document.querySelector("
                     "'div#jurisprudenciaresults_searchresults a[id^=\"ref-\"]'); "
                     "return a ? a.id : null; }")
    _JS_CAMBIAR_SELECT = ("([sel, v]) => { const s = document.querySelector(sel); "
                          "if (!s) return false; s.value = v; "
                          "if (s.value !== v) return false; "
                          "s.dispatchEvent(new Event('change', {bubbles: true})); return true; }")
    _JS_CARGANDO_OCULTO = ("() => { const l = document.querySelector('div.loading-results'); "
                           "return !l || l.offsetParent === null; }")

    async def _esperar_cambio(self, condicion_js: str, arg=None, timeout: int = 15000) -> bool:
        try:
            await self.page.wait_for_timeout(300)
            await self.page.wait_for_function(condicion_js, arg=arg, timeout=timeout)
            await self.page.wait_for_function(self._JS_CARGANDO_OCULTO, timeout=8000)
            return True
        except Exception:
            return False

    async def _resultados_por_pagina(self, n: int) -> None:
        """Cambia 'resultados por pagina' (10/20/30/50) al mayor valor <= n."""
        objetivo = next((o for o in (50, 30, 20) if o <= max(n, 10)), None)
        if not objetivo:
            return
        try:
            ok = await self.page.evaluate(
                self._JS_CAMBIAR_SELECT,
                ["select#frmFilterjurisprudencia_cboresults", str(objetivo)],
            )
            if ok:
                # El listado se ha recargado cuando hay mas de 10 tarjetas (o cuando
                # el total es <= 10 y no cambia nada; en ese caso expira sin dano).
                await self._esperar_cambio(
                    "() => document.querySelectorAll("
                    "'div#jurisprudenciaresults_searchresults div.searchresult').length > 10",
                    timeout=12000,
                )
        except Exception:
            pass  # nos quedamos con 10 por pagina

    _ORDEN = {
        "relevancia": "Relevance", "coincidencia": "Relevance",
        "fecha_desc": "IN_FECHARESOLUCION:decreasing", "fecha": "IN_FECHARESOLUCION:decreasing",
        "recientes": "IN_FECHARESOLUCION:decreasing", "reciente": "IN_FECHARESOLUCION:decreasing",
        "fecha_asc": "IN_FECHARESOLUCION:increasing", "antiguas": "IN_FECHARESOLUCION:increasing",
        "nuevo": "IN_FECHAENTRADA:numberdecreasing", "entrada": "IN_FECHAENTRADA:numberdecreasing",
        "organo": "IP_TIPOORGANO:alphabetical",
    }

    async def _ordenar(self, orden: str) -> None:
        """Cambia el criterio de orden. El sitio ordena por defecto por fecha de
        resolucion descendente, asi que ese valor no requiere recarga."""
        valor = self._ORDEN.get(_norm(orden).lower().replace(" ", "_"))
        if not valor or valor == "IN_FECHARESOLUCION:decreasing":
            return
        try:
            antes = await self.page.evaluate(self._JS_PRIMER_ID)
            ok = await self.page.evaluate(
                self._JS_CAMBIAR_SELECT, ["select#frmFilterjurisprudencia_cbosort", valor]
            )
            if ok:
                await self._esperar_cambio(
                    "(antes) => { const a = document.querySelector("
                    "'div#jurisprudenciaresults_searchresults a[id^=\"ref-\"]'); "
                    "return a && a.id !== antes; }",
                    arg=antes,
                )
        except Exception:
            pass

    async def _ir_a_pagina(self, pagina: int) -> None:
        """Salta directamente a la pagina N con la funcion global del sitio."""
        try:
            antes = await self.page.evaluate(self._JS_PRIMER_ID)
            ok = await self.page.evaluate(
                "(n) => { if (typeof goToPage !== 'function') return false; "
                "goToPage('jurisprudencia', n); return true; }",
                int(pagina),
            )
            if ok:
                await self._esperar_cambio(
                    "(antes) => { const a = document.querySelector("
                    "'div#jurisprudenciaresults_searchresults a[id^=\"ref-\"]'); "
                    "return a && a.id !== antes; }",
                    arg=antes,
                )
        except Exception:
            pass

    async def _marcar_multiselect(self, boton_sel: str, valores: list[str]) -> None:
        page = self.page
        grupo = page.locator(f'div.btn-group:has({boton_sel}) button.multiselect').first
        if not await grupo.count():
            return
        await grupo.click()
        await page.wait_for_timeout(400)
        for val in valores:
            li = page.locator(
                f'div.btn-group:has({boton_sel}) ul.multiselect-container li:has-text("{val}")'
            ).first
            if await li.count():
                chk = li.locator('input[type="checkbox"]')
                if await chk.count() and not await chk.is_checked():
                    await li.locator("label").click()
        await grupo.click()
        await page.wait_for_timeout(300)

    async def _parsear_tarjetas(self) -> list[dict]:
        page = self.page
        cards = page.locator('div#jurisprudenciaresults_searchresults div.searchresult')
        n = await cards.count()
        out: list[dict] = []
        for i in range(n):
            try:
                card = cards.nth(i)
                a = card.locator('a[id^="ref-"]').first
                if not await a.count():
                    continue
                titulo = " ".join((await a.inner_text()).split())
                href = _absolutizar(await a.get_attribute("href"))
                roj = await a.get_attribute("data-roj")
                roj = " ".join(roj.split()) if roj else None
                fechares = await a.get_attribute("data-fechares")
                fecha = None
                if fechares and len(fechares) == 8 and fechares.isdigit():
                    fecha = f"{fechares[6:8]}/{fechares[4:6]}/{fechares[:4]}"

                ecli = organo = sede = ponente = n_rec = n_res = None
                meta = card.locator("div.metadatos")
                if await meta.count():
                    t = await meta.inner_text()
                    ecli = _m(r"ECLI:\s*([^\s\n\r]+)", t)
                    if ecli and not ecli.upper().startswith("ECLI:"):
                        ecli = "ECLI:" + ecli
                    n_res = _m(r"N[ºo]\s*de Resoluci[oó]n:\s*([^\n\r]+?)(?=\s{2,}|$)", t)
                    n_rec = _m(r"N[ºo]\s*Recurso:\s*([^\s\n\r]+)", t)
                    sede = _m(r"Municipio:\s*([^\n\r]+?)(?=\s{2,}|$)", t)
                    ponente = _m(r"Ponente:\s*([^\n\r]+?)(?=\s{2,}|$)", t)
                if " - ROJ:" in titulo:
                    izq = titulo.split(" - ROJ:", 1)[0]
                    organo = izq.split(", a ", 1)[0].strip() if ", a " in izq else izq.strip()

                resumen = None
                h = card.locator("div.hddnsummary").first
                if await h.count():
                    resumen = (await h.inner_text()).strip()
                if resumen:
                    resumen = re.sub(r"\s*Ver m[aá]s.*$", "", resumen, flags=re.IGNORECASE)
                    resumen = " ".join(resumen.split())

                out.append({
                    "roj": roj, "ecli": ecli, "titulo": titulo, "fecha": fecha,
                    "organo": organo, "sede": sede, "ponente": ponente,
                    "n_recurso": n_rec, "n_resolucion": n_res,
                    "url": href, "resumen": resumen,
                })
            except Exception:
                continue
        return out

    async def resolver_pdf(self, url_ficha: str) -> tuple[str, dict]:
        """Fallback: abre la ficha y saca el enlace accessToPDF + cookies de sesion."""
        tp = await self.ctx.new_page()
        try:
            await tp.goto(url_ficha, timeout=20000)
            await tp.wait_for_load_state("networkidle")
            el = tp.locator('object[data*="accessToPDF"], a[href*="accessToPDF"]')
            real = None
            if await el.count():
                e0 = el.first
                tag = await e0.evaluate("el => el.tagName.toLowerCase()")
                real = await e0.get_attribute("data" if tag == "object" else "href")
            cookies = {c["name"]: c["value"] for c in await self.ctx.cookies()}
            return (_absolutizar(real) or url_ficha, cookies)
        finally:
            await tp.close()


# ---------------------------------------------------------------------------
# Obtencion de un documento (bytes + texto), con cache y fallbacks
# ---------------------------------------------------------------------------

async def obtener_documento(url_ficha: str) -> tuple[bytes | None, str]:
    """Devuelve (pdf_bytes, texto). Primero cache; luego httpx directo; por
    ultimo navegador. pdf_bytes puede ser None si solo habia texto en cache."""
    clave = _clave_doc(url_ficha)
    texto = _cache_get("txt:" + clave)
    data = _cache_get("pdf:" + clave)
    if texto and data:
        return data, texto
    if not data:
        directa = url_pdf_directa(url_ficha)
        if directa:
            data = await _descargar_pdf_httpx(directa)
        if not data:
            async with CendojBrowser() as br:
                real, cookies = await br.resolver_pdf(url_ficha)
                data = await _descargar_pdf_httpx(real, cookies)
        if not data:
            raise RuntimeError(
                f"No se pudo descargar el PDF de {url_ficha}. Comprueba la URL "
                "(debe ser la de buscar_sentencias) o reintenta mas tarde."
            )
        _cache_set("pdf:" + clave, data)
    if not texto:
        texto = _texto_de_pdf(data)
        _cache_set("txt:" + clave, texto)
    return data, texto


async def _localizar_por_cita(roj: str, ecli: str) -> dict | None:
    """Busca por ROJ/ECLI en el CENDOJ y devuelve la primera tarjeta (o None)."""
    cita = (roj or ecli or "").strip()
    obj = normalizar_cita(cita)
    roj_val = ecli_val = ""
    if isinstance(obj, Roj):
        roj_val = str(obj)
        e = roj_a_ecli(obj)
        ecli_val = str(e) if e else ""
    elif isinstance(obj, Ecli):
        ecli_val = str(obj)
    else:
        roj_val, ecli_val = roj.strip(), ecli.strip()
    async with CendojBrowser() as br:
        res = await br.buscar(roj=roj_val, ecli=ecli_val)
    return res["resultados"][0] if res["resultados"] else None


# ---------------------------------------------------------------------------
# API publica (async) usada por las tools del servidor
# ---------------------------------------------------------------------------

async def buscar_sentencias(
    consulta: str = "",
    jurisdiccion: str = "",
    localizacion: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    roj: str = "",
    ecli: str = "",
    ponente: str = "",
    norma: str = "",
    n_recurso: str = "",
    n_resolucion: str = "",
    pagina: int = 1,
    maximo: int = 10,
    orden: str = "",
) -> str:
    if not any([consulta, roj, ecli, ponente, norma, n_recurso, n_resolucion,
                fecha_desde, fecha_hasta]):
        return ("Indica al menos un criterio: consulta (texto libre), ROJ, ECLI, "
                "ponente, norma, nº de recurso/resolucion o un rango de fechas.")
    maximo = max(1, min(int(maximo or 10), 50))
    jur = [j.strip() for j in jurisdiccion.split(",") if j.strip()] if jurisdiccion else None
    loc = [l.strip() for l in localizacion.split(",") if l.strip()] if localizacion else None

    try:
        async with CendojBrowser() as br:
            res = await br.buscar(
                consulta=consulta, jurisdiccion=jur, localizacion=loc,
                fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, roj=roj, ecli=ecli,
                ponente=ponente, norma=norma, n_recurso=n_recurso,
                n_resolucion=n_resolucion, pagina=max(1, int(pagina or 1)),
                por_pagina=maximo, orden=orden,
            )
    except RuntimeError as e:
        return f"CENDOJ: {e}"
    except Exception as e:  # errores de Playwright/red
        return f"CENDOJ: fallo al consultar el buscador ({type(e).__name__}: {e})."

    total = res["total"]
    items = res["resultados"][:maximo]
    if not items:
        return f"Sin resultados en el CENDOJ para esa busqueda (total: {total})."

    out = [f"CENDOJ — {total} resultado(s). Pagina {pagina}, mostrando {len(items)}:", ""]
    for i, r in enumerate(items, 1):
        out.append(f"{i}. {r.get('roj') or r.get('titulo')}")
        linea = [x for x in (r.get("organo"), r.get("sede"), r.get("fecha")) if x]
        if linea:
            out.append("   " + " · ".join(linea))
        if r.get("ecli"):
            out.append(f"   {r['ecli']}")
        meta2 = []
        if r.get("n_resolucion"):
            meta2.append(f"Resolucion {r['n_resolucion']}")
        if r.get("n_recurso"):
            meta2.append(f"Recurso {r['n_recurso']}")
        if r.get("ponente"):
            meta2.append(f"Ponente: {r['ponente']}")
        if meta2:
            out.append("   " + " · ".join(meta2))
        if r.get("resumen"):
            resumen = r["resumen"]
            out.append(f"   Resumen: {resumen[:400]}{'…' if len(resumen) > 400 else ''}")
        if r.get("url"):
            out.append(f"   url: {r['url']}")
        out.append("")
    if total > len(items):
        out.append(f"Hay mas: repite con pagina={pagina + 1} (o sube `maximo` hasta 50).")
    out.append("Texto integro: `leer_sentencia` con la `url` (o ROJ/ECLI). Solo el fallo: "
               "seccion='fallo'. Pasajes sobre un tema: palabras_clave='...'.")
    return "\n".join(out)


async def leer_sentencia(
    url: str = "",
    roj: str = "",
    ecli: str = "",
    seccion: str = "todo",
    palabras_clave: str = "",
    guardar_pdf: bool = False,
    guardar_md: bool = False,
    ruta: str = "",
    max_chars: int = 45000,
) -> str:
    """Texto de una resolucion (entero, una seccion o los parrafos con ciertas
    palabras). Se identifica por url (openDocument) o por ROJ/ECLI."""
    meta: dict = {}
    try:
        if not url and (roj or ecli):
            meta = await _localizar_por_cita(roj, ecli) or {}
            url = meta.get("url") or ""
            if not url:
                return f"No encuentro «{roj or ecli}» en el CENDOJ. Revisa la cita."
        if not url:
            return "Indica la `url` de la sentencia (de buscar_sentencias) o su ROJ/ECLI."
        data, texto = await obtener_documento(url)
    except RuntimeError as e:
        return f"CENDOJ: {e}"
    except Exception as e:
        return f"CENDOJ: fallo al obtener la resolucion ({type(e).__name__}: {e})."

    if not texto.strip():
        return "Se descargo el documento pero no se pudo extraer texto (¿PDF escaneado?)."

    meta = {**{k: v for k, v in _meta_desde_texto(texto).items() if v}, **{k: v for k, v in meta.items() if v}}

    guardados = _guardar(meta, url, texto, data, guardar_pdf, guardar_md, ruta)

    # --- Que parte devolver ------------------------------------------------
    clave_sec = _ALIAS_SECCION.get((seccion or "todo").strip().lower(), None)
    cuerpo: str
    etiqueta_parte = ""
    if palabras_clave.strip():
        ps, modo = parrafos_con(texto, palabras_clave)
        if not ps:
            cuerpo = f"Ningun parrafo contiene «{palabras_clave}»."
        else:
            cuerpo = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(ps, 1))
        etiqueta_parte = f"Parrafos con «{palabras_clave}» ({len(ps)})"
        if modo == "alguna":
            etiqueta_parte += (" — AVISO: ningun parrafo contiene TODAS las palabras; "
                               "se muestran los que contienen alguna.")
    elif clave_sec and clave_sec != "todo":
        secs = secciones(texto)
        if clave_sec in secs:
            cuerpo = secs[clave_sec]
            etiqueta_parte = f"Seccion: {clave_sec.upper()}"
        else:
            disponibles = ", ".join(k for k in secs if k != "todo") or "ninguna reconocida"
            cuerpo = (f"No se ha localizado la seccion «{seccion}». Secciones detectadas: "
                      f"{disponibles}. Devuelvo el texto completo.\n\n{texto}")
    elif clave_sec is None:
        cuerpo = (f"Seccion «{seccion}» no reconocida (usa: fallo, fundamentos, "
                  f"antecedentes, hechos, encabezado, todo). Devuelvo el texto completo.\n\n{texto}")
    else:
        cuerpo = texto

    partes = [_cabecera(meta)]
    if etiqueta_parte:
        partes.append(etiqueta_parte)
    if guardados:
        partes.append("Guardado en:\n  " + "\n  ".join(guardados))
    cuerpo = truncar(cuerpo, max_chars, len(texto),
                     "seccion='fallo' o palabras_clave, o guardar_md=True para el fichero completo.",
                     titulo=meta.get("roj") or meta.get("ecli") or "Sentencia CENDOJ")
    partes.append(cuerpo)
    return "\n\n".join(p for p in partes if p)


async def descargar_sentencia(
    url: str = "",
    roj: str = "",
    ecli: str = "",
    formato: str = "pdf",
    ruta: str = "",
) -> str:
    """Guarda la resolucion en disco (pdf, md o ambos) sin volcar el texto al chat."""
    meta: dict = {}
    try:
        if not url and (roj or ecli):
            meta = await _localizar_por_cita(roj, ecli) or {}
            url = meta.get("url") or ""
            if not url:
                return f"No encuentro «{roj or ecli}» en el CENDOJ. Revisa la cita."
        if not url:
            return "Indica la `url` de la sentencia (de buscar_sentencias) o su ROJ/ECLI."
        data, texto = await obtener_documento(url)
    except RuntimeError as e:
        return f"CENDOJ: {e}"
    except Exception as e:
        return f"CENDOJ: fallo al obtener la resolucion ({type(e).__name__}: {e})."

    meta = {**{k: v for k, v in _meta_desde_texto(texto).items() if v}, **{k: v for k, v in meta.items() if v}}
    f = (formato or "pdf").strip().lower()
    quiere_pdf = f in ("pdf", "ambos", "los dos", "pdf+md", "md+pdf")
    quiere_md = f in ("md", "markdown", "ambos", "los dos", "pdf+md", "md+pdf")
    if not (quiere_pdf or quiere_md):
        return "formato debe ser 'pdf', 'md' o 'ambos'."
    guardados = _guardar(meta, url, texto, data, quiere_pdf, quiere_md, ruta)
    secs = secciones(texto)
    resumen_secs = ", ".join(k for k in secs if k != "todo") or "sin secciones reconocidas"
    return "\n".join([
        _cabecera(meta),
        f"Paginas/caracteres: {len(texto)} caracteres · secciones: {resumen_secs}",
        "Guardado en:\n  " + "\n  ".join(guardados),
    ])


# ---------------------------------------------------------------------------
# Utilidades de salida y ficheros
# ---------------------------------------------------------------------------

def _cabecera(meta: dict) -> str:
    partes = []
    if meta.get("roj"):
        partes.append(f"ROJ: {meta['roj']}")
    if meta.get("ecli"):
        partes.append(meta["ecli"] if meta["ecli"].upper().startswith("ECLI:") else f"ECLI: {meta['ecli']}")
    if meta.get("tipo"):
        partes.append(meta["tipo"])
    if meta.get("organo"):
        partes.append(meta["organo"])
    if meta.get("sede"):
        partes.append(meta["sede"])
    if meta.get("fecha"):
        partes.append(meta["fecha"])
    linea2 = []
    if meta.get("n_resolucion"):
        linea2.append(f"Resolucion {meta['n_resolucion']}")
    if meta.get("n_recurso"):
        linea2.append(f"Recurso {meta['n_recurso']}")
    if meta.get("procedimiento"):
        linea2.append(meta["procedimiento"])
    if meta.get("ponente"):
        linea2.append(f"Ponente: {meta['ponente']}")
    out = " · ".join(partes)
    if linea2:
        out += "\n" + " · ".join(linea2)
    return out


def _guardar(meta: dict, url: str, texto: str, data: bytes | None,
             pdf: bool, md: bool, ruta: str) -> list[str]:
    if not (pdf or md):
        return []
    etiqueta = _slug(meta.get("roj") or meta.get("ecli") or _clave_doc(url))
    destino = _dir_destino(ruta)
    out: list[str] = []
    if pdf and data:
        p = os.path.join(destino, f"{etiqueta}.pdf")
        with open(p, "wb") as f:
            f.write(data)
        out.append(p)
    if md:
        p = os.path.join(destino, f"{etiqueta}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_a_markdown(meta, url, texto))
        out.append(p)
    return out


def _dir_destino(ruta: str) -> str:
    return dir_destino(ruta, os.path.join(os.path.dirname(os.path.dirname(__file__)), "descargas"))


def _a_markdown(meta: dict, url: str, texto: str) -> str:
    m = meta or {}
    titulo = m.get("roj") or m.get("ecli") or "Resolución CENDOJ"
    lineas = [f"# {titulo}", "", "## Metadatos", ""]
    campos = [
        ("Tipo", m.get("tipo")), ("Fecha", m.get("fecha")), ("Órgano", m.get("organo")),
        ("Sede", m.get("sede")), ("Sección", m.get("seccion")), ("Ponente", m.get("ponente")),
        ("Procedimiento", m.get("procedimiento")),
        ("Nº Resolución", m.get("n_resolucion")), ("Nº Recurso", m.get("n_recurso")),
        ("ROJ", m.get("roj")), ("ECLI", m.get("ecli")), ("Id Cendoj", m.get("id_cendoj")),
    ]
    for k, v in campos:
        if v:
            lineas.append(f"- **{k}**: {v}")
    lineas.append(f"- **Fuente**: [{url}]({url})")
    secs = secciones(texto)
    if "todo" in secs:
        lineas += ["", "---", "", "## Texto íntegro", "", texto]
    else:
        orden = ["encabezado", "antecedentes", "hechos", "fundamentos", "fallo"]
        titulos = {"encabezado": "Encabezado", "antecedentes": "Antecedentes de hecho",
                   "hechos": "Hechos probados", "fundamentos": "Fundamentos de derecho",
                   "fallo": "Fallo"}
        for k in orden:
            if k in secs:
                lineas += ["", "---", "", f"## {titulos[k]}", "", secs[k]]
    return "\n".join(lineas)
