"""Tests del modulo Catastro.

Se dividen en:
  - Offline (siempre): normalizacion, deteccion foral, validacion de RC,
    troceo de direcciones y mensajes de guia. No tocan la red.
  - Red (marcados 'red'): golpean los servicios OVC oficiales del Catastro
    (Callejero WCF/JSON y Coordenadas ASMX). Se saltan con  -m 'not red'.
    Referencia catastral publica usada como oraculo: 0545206VK4704F0001RE
    (Calle de Alcala 1, Madrid; uso Oficinas; año 1880).
"""

import pytest

from sources import catastro as c


# ------------------------------- offline -----------------------------------

def test_norm_sin_tildes_mayusculas():
    assert c._norm("Calle Alcalá") == "CALLE ALCALA"
    assert c._norm("  a  coruña ") == "A CORUÑA"


def test_es_foral_por_nombre():
    assert c._es_foral("VIZCAYA")
    assert c._es_foral("Bizkaia")
    assert c._es_foral("Navarra")
    assert c._es_foral("Gipuzkoa")
    assert not c._es_foral("MADRID")


def test_es_foral_por_codigo_provincia():
    assert c._es_foral(cp="48")   # Bizkaia
    assert c._es_foral(cp="1")    # Araba (se rellena a '01')
    assert c._es_foral(cp="31")   # Navarra
    assert not c._es_foral(cp="28")  # Madrid


def test_limpiar_rc():
    assert c._limpiar_rc(" 0545206vk4704f0001re ") == "0545206VK4704F0001RE"


def test_partir_direccion_deduce_sigla_y_numero():
    assert c._partir_direccion("Calle Alcala 1", "", "") == ("CL", "ALCALA", "1")
    assert c._partir_direccion("Plaza Mayor 3", "", "") == ("PZ", "MAYOR", "3")
    assert c._partir_direccion("Avenida de America", "AV", "10") == ("AV", "DE AMERICA", "10")


def test_partir_direccion_sin_prefijo():
    # Sin tipo de via reconocible: sigla vacia, via en mayusculas.
    assert c._partir_direccion("Gran Via 28", "", "") == ("", "GRAN VIA", "28")


def test_fmt_sup():
    assert c._fmt_sup("3.276") == "3276 m2"
    assert c._fmt_sup("899") == "899 m2"
    assert c._fmt_sup(None) == "?"


def test_aviso_foral_sin_red():
    out = c.consultar_catastro(direccion="Gran Via 1", municipio="BILBAO",
                               provincia="VIZCAYA")
    assert "foral" in out.lower()
    assert "Bizkaia" in out or "Pais Vasco" in out


def test_rc_invalida_mensaje():
    out = c.consultar_catastro(referencia_catastral="ABC")
    assert "no valida" in out.lower()


def test_coordenadas_invalidas_mensaje():
    out = c.consultar_catastro(coordenadas="esto no son coordenadas")
    assert "no validas" in out.lower()


def test_sin_criterio_mensaje():
    out = c.consultar_catastro()
    assert "via de busqueda" in out.lower()


# --------------------------------- red -------------------------------------

@pytest.mark.red
def test_rc_alcala_datos_no_protegidos():
    """Oraculo: Calle Alcala 1, Madrid. Oficinas, 1880, sin titular ni valor."""
    out = c.consultar_catastro(referencia_catastral="0545206VK4704F0001RE")
    assert "0545206VK4704F0001RE" in out
    assert "Oficinas" in out
    assert "1880" in out
    assert "Urbana" in out
    # Nunca debe filtrar datos protegidos.
    assert "titular" not in out.lower() or "NO facilita titular" in out


@pytest.mark.red
def test_direccion_resuelve_referencia():
    out = c.consultar_catastro(direccion="Calle Alcala 1", municipio="MADRID",
                               provincia="MADRID")
    assert "0545206VK4704F" in out


@pytest.mark.red
def test_coordenadas_devuelven_referencia():
    out = c.consultar_catastro(coordenadas="40.417249,-3.702166")
    assert "0545206VK4704F" in out


@pytest.mark.red
def test_rustica_poligono_parcela():
    out = c.consultar_catastro(poligono="1", parcela="1", municipio="VALDEPEÑAS",
                               provincia="CIUDAD REAL")
    assert "Rustica" in out
    assert "13087A" in out


@pytest.mark.red
def test_callejero_provincias():
    out = c.callejero_catastro()
    assert "MADRID" in out
    assert "BARCELONA" in out
    # Foral fuera del listado.
    assert "BIZKAIA" not in out and "NAVARRA" not in out


@pytest.mark.red
def test_callejero_vias_filtra():
    out = c.callejero_catastro(municipio="MADRID", provincia="MADRID", via="Alcala")
    assert "CL ALCALA" in out


@pytest.mark.red
def test_callejero_municipios_de_provincia():
    out = c.callejero_catastro(provincia="MADRID")
    assert "MADRID" in out
