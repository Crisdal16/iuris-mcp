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
