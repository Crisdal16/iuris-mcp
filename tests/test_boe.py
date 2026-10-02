"""Tests del modulo BOE.

Se dividen en:
  - Offline (siempre): resolucion de siglas y normalizacion de articulos/fechas.
  - Red (marcados 'red'): golpean la API oficial de datos abiertos del BOE.
    Se saltan con  pytest -m "not red".  Los valores esperados se verificaron
    ademas contra Jurisprudenciator (oraculo).
"""

import pytest

from sources import boe


# ------------------------------- offline -----------------------------------

def test_resolver_sigla():
    assert boe.resolver_norma("LEC") == "BOE-A-2000-323"
    assert boe.resolver_norma("cc") == "BOE-A-1889-4763"


def test_resolver_nombre_largo():
    assert boe.resolver_norma("Código Civil") == "BOE-A-1889-4763"


def test_resolver_boe_id_passthrough():
    assert boe.resolver_norma("BOE-A-2000-323") == "BOE-A-2000-323"


def test_resolver_desconocida():
    assert boe.resolver_norma("Ley de Narnia") is None


@pytest.mark.parametrize("entrada,clave", [
    ("Artículo 394. Condena en las costas.", "394"),
    ("Art 1902", "1902"),
    ("art. 138", "138"),
    ("Artículo 439 bis", "439 BIS"),
])
def test_clave_articulo_normaliza_formatos(entrada, clave):
    assert boe._clave_articulo(entrada) == clave


def test_fecha_api():
    assert boe._fecha_api("2026-08-14") == "20260814"
    assert boe._fecha_api("14/08/2026") == "20260814"
    assert boe._fecha_api("20260814") == "20260814"
    assert boe._fecha_api("ayer") is None


def test_articulo_norma_desconocida_mensaje():
    assert "No reconozco" in boe.buscar_articulo("Ley de Narnia", "1")


# --------------------------------- red -------------------------------------

@pytest.mark.red
def test_articulo_cc_1902_texto_vigente():
    """Oraculo: coincide palabra por palabra con Jurisprudenciator."""
    out = boe.buscar_articulo("CC", "1902")
    assert "acción u omisión causa daño a otro" in out
    assert "BOE-A-1889-4763" in out


@pytest.mark.red
def test_articulo_lec_394():
    out = boe.buscar_articulo("LEC", "394")
    assert "costas de la primera instancia" in out.lower()


@pytest.mark.red
def test_articulo_formato_art_antiguo_y_nuevo():
    """El CC usa 'Art 1902'; la LEC usa 'Artículo 394'. Ambos deben resolver."""
    assert "Art 1902" in boe.buscar_articulo("CC", "1902")
    assert "Artículo 394" in boe.buscar_articulo("LEC", "394")


@pytest.mark.red
def test_sumario_boe_extrae_items():
    out = boe.sumario_boe("14/08/2026")
    assert "BOE-A-2026-" in out
    assert "entradas" in out


@pytest.mark.red
def test_buscar_boe_por_titulo():
    out = boe.buscar_boe("vivienda", limite=3)
    assert "vivienda" in out.lower()
    assert "BOE-A-" in out


@pytest.mark.red
def test_novedades_boe_rango_corto():
    out = boe.novedades_boe("Universidad", "2026-08-13", "2026-08-14")
    assert "Universidad" in out


def test_novedades_boe_rango_excesivo():
    assert "31 dias" in boe.novedades_boe("x", "2026-01-01", "2026-12-31")


def test_buscar_boe_vacia():
    assert "Indica" in boe.buscar_boe("   ")


# ------------------------- version vigente (regresion) ----------------------

def _v(fecha, norma):
    import xml.etree.ElementTree as ET
    return ET.fromstring(f'<version id_norma="{norma}" fecha_vigencia="{fecha}"/>')


def test_elegir_version_toma_la_vigente_no_la_original():
    """Bug real: se devolvia la PRIMERA <version> (redaccion original de 2001)."""
    vs = [_v("20010108", "BOE-A-2000-323"), _v("20111031", "BOE-A-2011-15937"),
          _v("20240320", "BOE-A-2023-25758")]
    actual, futura = boe.elegir_version(vs, hoy="20261002")
    assert actual.get("id_norma") == "BOE-A-2023-25758"
    assert futura is None


def test_elegir_version_avisa_de_redaccion_futura():
    vs = [_v("20010108", "A"), _v("20240320", "B"), _v("20270101", "C")]
    actual, futura = boe.elegir_version(vs, hoy="20261002")
    assert actual.get("id_norma") == "B"
    assert futura.get("id_norma") == "C"


@pytest.mark.parametrize("texto,esperado", [
    ("Ley 29/1998", ("LEY", "29/1998")),
    ("Ley Orgánica 3/2018", ("LO", "3/2018")),
    ("LO 10/1995", ("LO", "10/1995")),
    ("Real Decreto Legislativo 8/2015", ("RDLEG", "8/2015")),
    ("RDLeg 1/2020", ("RDLEG", "1/2020")),
    ("Real Decreto-ley 8/2020", ("RDL", "8/2020")),
    ("RD 1065/2007", ("RD", "1065/2007")),
    ("Ley de Narnia", None),
])
def test_parsear_rango_numero(texto, esperado):
    assert boe.parsear_rango_numero(texto) == esperado


@pytest.mark.red
def test_articulo_455_lec_redaccion_vigente():
    out = boe.buscar_articulo("LEC", "455")
    assert "cinco días" not in out.split("Notas del BOE")[0]
    assert "3.000 euros" in out


@pytest.mark.red
def test_resolver_por_numero_ljca():
    assert boe.resolver_norma("Ley 29/1998") == "BOE-A-1998-16718"


@pytest.mark.red
def test_buscar_boe_busca_en_servidor():
    out = boe.buscar_boe("arrendamientos urbanos", limite=5)
    assert "BOE-A-1994-26003" in out
