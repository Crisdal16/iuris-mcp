"""Tests offline del modulo CENDOJ en vivo.

Solo cubren la logica pura (normalizacion de filtros, fechas, slug, URL directa
del PDF, cabecera del PDF, secciones y parrafos). El acceso real al CENDOJ
(Playwright/httpx) NO se prueba aqui: es un test de red y queda fuera de la
suite offline.
"""

from sources.cendoj_live import (
    _clave_doc,
    _fecha,
    _label_jurisdiccion,
    _label_localizacion,
    _meta_desde_texto,
    _slug,
    parrafos,
    parrafos_con,
    secciones,
    url_pdf_directa,
)

CABECERA = (
    "JURISPRUDENCIA\n"
    "Roj: STSJ MU 1411/2026 - ECLI:ES:TSJMU:2026:1411\n"
    "Id Cendoj: 30030340012026100664\n"
    "Órgano: Tribunal Superior de Justicia. Sala de lo Social\n"
    "Sede: Murcia\n"
    "Sección: 1\n"
    "Fecha: 20/07/2026\n"
    "Nº de Recurso: 29/2026\n"
    "Nº de Resolución: 696/2026\n"
    "Procedimiento: Recurso de suplicación\n"
    "Ponente: MARIA DOLORES NOGUEROLES PEÑA\n"
    "Tipo de Resolución: Sentencia\n"
)

SENTENCIA = CABECERA + (
    "TRIBUNAL SUPERIOR DE JUSTICIA DE MURCIA\n"
    "ANTECEDENTES DE HECHO\n"
    "PRIMERO.- La parte actora presentó demanda.\n"
    "SEGUNDO.- Se dictó sentencia cuyo fallo dice:\n"
    "FALLO\n"
    "Que estimo la demanda.\n"
    "FUNDAMENTOS DE DERECHO\n"
    "PRIMERO.- Sobre la cláusula suelo y su transparencia.\n"
    "El control de transparencia exige información\n"
    "comprensible al consumidor.\n"
    "SEGUNDO.- Costas.\n"
    "FALLAMOS\n"
    "Que desestimamos el recurso de suplicación.\n"
)

# --- Jurisdiccion -> value de la <option> del formulario --------------------
# Regresion: antes se buscaba un boton '..._JURISDICCIONmultiselec' que no existe
# y el filtro se ignoraba en silencio (STS civiles al pedir 'Penal').

def test_jurisdiccion_contencioso_variantes():
    assert _label_jurisdiccion("contencioso") == "CONTENCIOSO"
    assert _label_jurisdiccion("Contencioso-Administrativo") == "CONTENCIOSO"
    assert _label_jurisdiccion("CONTENCIOSO ADMINISTRATIVO") == "CONTENCIOSO"


def test_jurisdiccion_basicas_y_sinonimos():
    assert _label_jurisdiccion("civil") == "CIVIL"
    assert _label_jurisdiccion("Penal") == "PENAL"
    assert _label_jurisdiccion("SOCIAL") == "SOCIAL"
    assert _label_jurisdiccion("laboral") == "SOCIAL"
    assert _label_jurisdiccion("militar") == "MILITAR"
    assert _label_jurisdiccion("especial") == "ESPECIAL"


def test_jurisdiccion_desconocida():
    assert _label_jurisdiccion("mercantil") is None


# --- Localizacion: provincia -> CCAA; CCAA pasa tal cual --------------------

def test_localizacion_provincia_a_ccaa():
    assert _label_localizacion("Barcelona") == "Cataluña"
    assert _label_localizacion("bilbao") == "País Vasco"
    assert _label_localizacion("Murcia") == "Murcia"
    assert _label_localizacion("Cartagena") == "Murcia"
    assert _label_localizacion("Valladolid") == "Castilla y León"


def test_localizacion_ccaa_se_respeta():
    assert _label_localizacion("Cataluña") == "Cataluña"
    assert _label_localizacion("Comunidad Valenciana") == "Comunidad Valenciana"


def test_localizacion_nombres_del_formulario():
    # Regresion: el panel del CENDOJ dice "BALEARES" y "CASTILLA LA MANCHA".
    assert _label_localizacion("Islas Baleares") == "Baleares"
    assert _label_localizacion("Palma") == "Baleares"
    assert _label_localizacion("Castilla-La Mancha") == "Castilla La Mancha"
    assert _label_localizacion("Toledo") == "Castilla La Mancha"


# --- Fechas -----------------------------------------------------------------

def test_fecha_iso_a_es():
    assert _fecha("2026-09-16") == "16/09/2026"


def test_fecha_ya_es_o_vacia():
    assert _fecha("16/09/2026") == "16/09/2026"
    assert _fecha("") == ""


# --- URL directa del PDF (patron verificado en el sitio) --------------------

def test_url_pdf_directa_desde_ficha():
    ficha = "https://www.poderjudicial.es/search/AN/openDocument/a54fa5df96fdc558a0a8778d75e36f0d/20260810"
    u = url_pdf_directa(ficha)
    assert u is not None
    assert "action=accessToPDF" in u
    assert "reference=a54fa5df96fdc558a0a8778d75e36f0d" in u
    assert "optimize=20260810" in u
    assert _clave_doc(ficha) == "a54fa5df96fdc558a0a8778d75e36f0d"


def test_url_pdf_directa_no_encaja():
    assert url_pdf_directa("https://www.poderjudicial.es/search/indexAN.jsp") is None


# --- Slug para nombre de fichero -------------------------------------------

def test_slug_desde_roj_y_ecli():
    assert _slug("STSJ MU 1411/2026") == "STSJ_MU_1411-2026"
    assert _slug("ECLI:ES:TSJMU:2026:1411") == "ECLI_ES_TSJMU_2026_1411"


def test_slug_vacio_por_defecto():
    assert _slug("") == "documento"


# --- Metadatos desde la cabecera del PDF -----------------------------------

def test_meta_desde_texto():
    meta = _meta_desde_texto(CABECERA)
    assert meta["roj"] == "STSJ MU 1411/2026"
    assert meta["ecli"] == "ECLI:ES:TSJMU:2026:1411"
    assert meta["id_cendoj"] == "30030340012026100664"
    assert meta["sede"] == "Murcia"
    assert meta["fecha"] == "20/07/2026"
    assert meta["n_recurso"] == "29/2026"
    assert meta["n_resolucion"] == "696/2026"
    assert meta["procedimiento"] == "Recurso de suplicación"
    assert meta["tipo"] == "Sentencia"
    assert "NOGUEROLES" in meta["ponente"]


# --- Secciones -------------------------------------------------------------

def test_secciones_detecta_las_cuatro():
    s = secciones(SENTENCIA)
    assert set(s) >= {"encabezado", "antecedentes", "fundamentos", "fallo"}
    assert "Roj:" in s["encabezado"]
    assert s["antecedentes"].startswith("ANTECEDENTES DE HECHO")
    assert "cláusula suelo" in s["fundamentos"]


def test_secciones_fallo_es_el_ultimo():
    # El 'FALLO' citado dentro de los antecedentes NO debe ganar al FALLAMOS final.
    s = secciones(SENTENCIA)
    assert s["fallo"].startswith("FALLAMOS")
    assert "desestimamos el recurso" in s["fallo"]
    assert "estimo la demanda" not in s["fallo"]


def test_secciones_sin_cabeceras():
    assert secciones("texto plano sin estructura") == {"todo": "texto plano sin estructura"}


def test_secciones_no_confunde_minusculas():
    # 'fallo' en minusculas dentro de una frase no es cabecera.
    t = "ANTECEDENTES DE HECHO\nel fallo\nno es cabecera.\nFALLO\nSe estima.\n"
    s = secciones(t)
    assert s["fallo"] == "FALLO\nSe estima."


# --- Parrafos --------------------------------------------------------------

def test_parrafos_reagrupa_lineas():
    ps = parrafos(SENTENCIA)
    junto = [p for p in ps if "comprensible al consumidor" in p]
    assert junto and "exige información comprensible" in junto[0]


def test_parrafos_con_todas_las_palabras():
    ps, modo = parrafos_con(SENTENCIA, "clausula suelo transparencia")
    assert modo == "todas"
    assert len(ps) == 1
    assert "cláusula suelo" in ps[0]


def test_parrafos_con_fallback_a_alguna():
    ps, modo = parrafos_con(SENTENCIA, "costas inexistente_xyz")
    assert modo == "alguna"
    assert ps and "Costas" in ps[0]


def test_parrafos_con_sin_claves():
    assert parrafos_con(SENTENCIA, "  ") == ([], "ninguna")
    assert parrafos_con(SENTENCIA, "zzz_nada") == ([], "ninguna")


# ---------------------------------------------------------------------------
# Captcha «Descargas masivas» y diagnóstico de descarga (fix 2026-11)
# ---------------------------------------------------------------------------

import asyncio

import pytest

import sources.cendoj_live as cl

CAPTCHA_HTML = (
    '<html><head><title>CENDOJ : Buscador del Sistema de Jurisprudencia</title></head>'
    '<body><span class="area">Control </span> <span class="restring">Descargas masivas</span>'
    '<h2>Por favor, introduzca el texto que muestra la siguiente imagen:</h2>'
    '<form action="contenidos.action" name="frmauthenticatecaptcha" method="POST">'
    '<input type="hidden" name="action" value="captcha"/>'
)

FICHA = ("https://www.poderjudicial.es/search/AN/openDocument/"
         "53db339e63caa793a0a8778d75e36f0d/20251024")


def test_es_captcha_por_url():
    assert cl._es_captcha("https://www.poderjudicial.es/search/captcha.jsp"
                       "?prevaction=accessToPDF&publicinterface=true&tab=AN")


def test_es_captcha_por_contenido():
    assert cl._es_captcha("https://www.poderjudicial.es/search/contenidos.action", CAPTCHA_HTML)
    assert cl._es_captcha("https://x", b"<html>frmauthenticatecaptcha</html>")


def test_no_es_captcha():
    assert not cl._es_captcha("https://www.poderjudicial.es/search/contenidos.action", "%PDF-1.7")
    assert not cl._es_captcha("https://www.poderjudicial.es/search/indexAN.jsp", "<html>hola</html>")


def test_error_captcha_es_runtimeerror_con_enlace_oficial():
    e = cl.ErrorCaptcha("https://www.poderjudicial.es/search/contenidos.action"
                        "?action=accessToPDF&reference=53db", "https://x/captcha.jsp")
    assert isinstance(e, RuntimeError)
    assert "captcha" in str(e).lower()
    assert "accessToPDF" in str(e)          # trae el enlace oficial del PDF
    assert e.url_pdf.endswith("reference=53db")


def test_ejecutable_chromium_desde_entorno(monkeypatch):
    monkeypatch.delenv("IURIS_CHROMIUM_PATH", raising=False)
    assert _es_none(cl._ejecutable_chromium())
    monkeypatch.setenv("IURIS_CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    assert cl._ejecutable_chromium() == "/opt/pw-browsers/chromium"
    monkeypatch.setenv("IURIS_CHROMIUM_PATH", "   ")
    assert _es_none(cl._ejecutable_chromium())


def _es_none(x):
    return x is None


def test_descargar_pdf_httpx_captcha(monkeypatch, capsys):
    """Si el servidor devuelve el HTML del captcha, levanta ErrorCaptcha."""

    class _Resp:
        status_code = 200
        headers = {"content-type": "text/html"}
        url = "https://www.poderjudicial.es/search/captcha.jsp?prevaction=accessToPDF"
        content = CAPTCHA_HTML.encode("utf-8")

    class _Cli:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return _Resp()

    class _Httpx:
        AsyncClient = _Cli

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    with pytest.raises(cl.ErrorCaptcha):
        asyncio.run(cl._descargar_pdf_httpx("https://x/contenidos.action"))
    assert "captcha.jsp" in _Resp.url


def test_descargar_pdf_httpx_red_visible(monkeypatch, capsys):
    """Un fallo de red/TLS ya NO se traga en silencio: avisa por stderr."""

    import httpx as _httpx_real

    class _Cli:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            raise _httpx_real.ConnectError("tls: certificado del proxy no confia")

    class _Httpx:
        AsyncClient = _Cli

    monkeypatch.setitem(__import__("sys").modules, "httpx", _Httpx)
    assert asyncio.run(cl._descargar_pdf_httpx("https://x")) is None
    salida = capsys.readouterr().err
    assert "iuris.cendoj" in salida
    assert "ConnectError" in salida or "sin conexion" in salida


def test_obtener_documento_captcha_no_insiste_con_navegador(monkeypatch):
    """Con captcha se corta en la descarga directa: el navegador chocaria igual."""

    async def captcha(url, cookies=None):
        raise cl.ErrorCaptcha("pdf-url", "captcha-url")

    class _NoBrowser:
        def __init__(self):
            raise AssertionError("no debio abrirse el navegador tras un captcha")

    monkeypatch.setattr(cl, "_descargar_pdf_httpx", captcha)
    monkeypatch.setattr(cl, "CendojBrowser", _NoBrowser)
    with pytest.raises(cl.ErrorCaptcha):
        asyncio.run(cl.obtener_documento(FICHA))


def test_obtener_documento_fallo_generico_explica_causas(monkeypatch):
    async def nada(url, cookies=None):
        return None

    class _Br:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def resolver_pdf(self, url): return ("https://x/real", {})

    monkeypatch.setattr(cl, "_descargar_pdf_httpx", nada)
    monkeypatch.setattr(cl, "CendojBrowser", _Br)
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(cl.obtener_documento(FICHA))
    assert "captcha" in str(ei.value).lower()


def test_localizar_por_cita_reintenta_por_resolucion(monkeypatch):
    """«STS 4452/2025» sin ROJ valido: reintenta como nº de resolucion y avisa."""

    class _FakeBr:
        def __init__(self):
            self.busquedas = []

        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def buscar(self, **k):
            self.busquedas.append(k)
            if k.get("roj") or k.get("ecli"):
                return {"total": 0, "resultados": []}
            return {"total": 1, "resultados": [{
                "roj": "STSJ MU 1791/2025", "ecli": "ECLI:ES:TSJMU:2025:1791",
                "url": "https://www.poderjudicial.es/search/AN/openDocument/"
                       "ab" * 16 + "/20251024"}]}

    fake = _FakeBr()
    monkeypatch.setattr(cl, "CendojBrowser", lambda: fake)
    tarjeta = asyncio.run(cl._localizar_por_cita("STS 4452/2025", ""))
    assert tarjeta["roj"] == "STSJ MU 1791/2025"
    assert "aviso_localizacion" in tarjeta
    assert "4452/2025" in tarjeta["aviso_localizacion"]
    assert any(k.get("n_resolucion") == "4452/2025" for k in fake.busquedas)


def test_localizar_por_cita_sin_nada(monkeypatch):
    class _FakeBr:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def buscar(self, **k):
            return {"total": 0, "resultados": []}

    monkeypatch.setattr(cl, "CendojBrowser", _FakeBr)
    assert asyncio.run(cl._localizar_por_cita("STS 99999/2099", "")) is None
