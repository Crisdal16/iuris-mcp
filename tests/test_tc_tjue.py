"""Tests offline de TC (buscador HJ) y TJUE (CELLAR): solo logica pura.

El acceso real (HTTP) queda fuera de la suite offline.
"""

from common.texto import norm, parrafos_con, slug, texto_de_html, truncar
from sources.tc import _RE_CITA_TC, _fecha, _parsear_lista, _TIPO
from sources.tjue import _RE_CELEX, _anio4, a_celex_candidatos

# --- TJUE: CELEX -----------------------------------------------------------

def test_celex_desde_asunto_tribunal_justicia():
    assert a_celex_candidatos("C-311/18") == ["62018CJ0311"]
    assert a_celex_candidatos("c-6/64") == ["61964CJ0006"]


def test_celex_desde_asunto_tribunal_general():
    assert a_celex_candidatos("T-778/16") == ["62016TJ0778"]


def test_celex_conclusiones_y_auto():
    assert a_celex_candidatos("C-311/18", tipo="conclusiones") == ["62018CC0311"]
    assert a_celex_candidatos("C-311/18", tipo="auto") == ["62018CO0311"]
    assert a_celex_candidatos("T-778/16", tipo="auto") == ["62016TO0778"]


def test_celex_directo_y_no_reconocido():
    assert a_celex_candidatos("62018CJ0311") == ["62018CJ0311"]
    assert _RE_CELEX.match("62018CJ0311")
    assert a_celex_candidatos("Schrems II") == []


def test_anio4():
    assert _anio4("18") == "2018"
    assert _anio4("64") == "1964"
    assert _anio4("2020") == "2020"


# --- TC: citas y fechas ----------------------------------------------------

def test_cita_tc():
    m = _RE_CITA_TC.match("STC 31/2010")
    assert m and m.group("num") == "31" and m.group("anio") == "2010"
    assert _TIPO[m.group("tipo").upper()] == "SENTENCIA"
    assert _RE_CITA_TC.match("atc 12/2020")
    assert _RE_CITA_TC.match("STS 1177/2014") is None


def test_fecha_tc():
    assert _fecha("2026-09-17") == "17/09/2026"
    assert _fecha("17/09/2026") == "17/09/2026"


def test_parsear_lista_tc_dedup_y_campos():
    html = """
    <div>Sentencia (20) Auto (7) Todos (27)</div>
    <ul id="resolution-list">
      <li class="even">
        <a href="/HJ/es/Resolucion/Show/32103">1. Sala Segunda. SENTENCIA 47/2026, de 22 de junio</a>
        <a href="/HJ/es/Resolucion/Show/32103">ver</a>
        <p>Tipo de Proceso</p><p>Recurso de amparo 8456-2025</p>
        <p>Síntesis Descriptiva</p><p>Promovido por don X respecto de resoluciones de un juzgado.</p>
        <p>Síntesis Analítica</p><p>Vulneración del derecho a la tutela judicial efectiva.</p>
      </li>
      <li class="odd"><a href="/HJ/es/Resolucion/Show/0">plantilla</a></li>
    </ul>"""
    total, res = _parsear_lista(html)
    assert total == 27
    assert len(res) == 1
    r = res[0]
    assert r["id"] == "32103"
    assert r["titulo"].startswith("1. Sala Segunda. SENTENCIA 47/2026")
    assert r["tipo_proceso"] == "Recurso de amparo 8456-2025"
    assert "Promovido por don X" in r["sintesis_descriptiva"]
    assert "tutela judicial" in r["sintesis_analitica"]
    assert r["url"].endswith("/Show/32103")


# --- common.texto ----------------------------------------------------------

def test_norm_y_slug():
    assert norm("Cláusula Suelo") == "CLAUSULA SUELO"
    assert slug("ECLI:ES:TC:2010:31") == "ECLI_ES_TC_2010_31"


def test_texto_de_html_limpia():
    from selectolax.parser import HTMLParser
    t = HTMLParser("<div><script>x</script><p>Hola&nbsp; mundo</p>\n\n<p>  Dos </p></div>")
    assert texto_de_html(t.css_first("div")) == "Hola mundo\nDos"


def test_truncar():
    assert truncar("abc", 10, 3, "x") == "abc"
    out = truncar("a" * 20, 5, 100, "consejo")
    assert out.startswith("aaaaa\n\n[…truncado a 5 de 20")
    assert "consejo" in out


def test_parrafos_con_modo():
    ps, modo = parrafos_con("Uno con perro.\nDos con gato.\n", "perro gato")
    assert modo == "alguna" and len(ps) == 2
