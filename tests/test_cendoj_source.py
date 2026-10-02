"""Tests del modulo CENDOJ 'humano en el bucle'.

Se centran en que la logica que aporta valor (traduccion de filtros, deteccion
de autos, descomposicion de Id Cendoj, construccion de URL) sea correcta.
Ninguno toca la red: el modulo no descarga del CENDOJ por diseno.
"""

from sources import cendoj


# ---------------------------------------------------------------------------
# construir_busqueda
# ---------------------------------------------------------------------------

def test_busqueda_incluye_url_del_navegador():
    out = cendoj.construir_busqueda("clausula suelo")
    assert "poderjudicial.es/search/sentencias/" in out
    assert "clausula" in out.lower()


def test_busqueda_normaliza_tildes_en_la_url():
    out = cendoj.construir_busqueda("cláusula suelo transparencia")
    # La URL va sin tildes; el texto humano puede llevarlas.
    assert "clausula%20suelo%20transparencia" in out


def test_busqueda_traduce_provincia_y_organo():
    out = cendoj.construir_busqueda(
        "Confederacion Hidrografica del Segura",
        tipo_organo="TSJ", provincia="Murcia",
    )
    assert "33" in out                     # codigo de organo TSJ Contencioso
    assert "MU" in out                     # sigla de Murcia
    assert "Localizacion" in out


def test_busqueda_provincia_fuerza_base_an():
    out = cendoj.construir_busqueda("x", base="TS", provincia="Valladolid")
    assert "/1/AN" in out                  # se ajusta a AN
    assert "VA" in out


def test_busqueda_vacia_avisa():
    assert "Indica una consulta" in cendoj.construir_busqueda("   ")


def test_busqueda_organo_no_reconocido_no_rompe():
    out = cendoj.construir_busqueda("x", tipo_organo="INVENTADO")
    assert "no reconocido" in out.lower()


# ---------------------------------------------------------------------------
# analizar_cita
# ---------------------------------------------------------------------------

def test_analizar_roj_sentencia():
    out = cendoj.analizar_cita("STS 1177/2014")
    assert "ECLI:ES:TS:2014:1177" in out
    assert "SENTENCIA" in out


def test_analizar_auto_avisa_de_la_A():
    out = cendoj.analizar_cita("AAP B 9672/2019")
    assert "AUTO" in out
    assert "ECLI:ES:APB:2019:9672A" in out
    assert "'A'" in out                    # avisa de la 'A' final


def test_analizar_id_cendoj_descompone():
    out = cendoj.analizar_cita("30030330022026100387")
    assert "30030" in out                  # Murcia
    assert "33" in out                     # organo
    assert "CONTENCIOSO" in out.upper()


def test_analizar_ecli_tjue():
    out = cendoj.analizar_cita("C-311/19")
    assert "TJUE" in out
    assert "C-311/19" in out


def test_analizar_cita_invalida():
    assert "No reconozco" in cendoj.analizar_cita("hola que tal")
