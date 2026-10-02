"""Tests del modulo MERCANTIL (BORME via API de datos abiertos del BOE).

  - Offline (siempre): fechas, normalizacion, deteccion de seccion/CIF y el
    modo humano-en-el-bucle de buscar_empresa_mercantil (sin red).
  - Red (marcados 'red'): golpean la API oficial del BORME. Se saltan con
    pytest -m "not red".
"""

import pytest

from sources import mercantil


# ------------------------------- offline -----------------------------------

def test_fecha_api():
    assert mercantil._fecha_api("2026-08-14") == "20260814"
    assert mercantil._fecha_api("14/08/2026") == "20260814"
    assert mercantil._fecha_api("20260814") == "20260814"
    assert mercantil._fecha_api("ayer") is None


def test_norm_sin_tildes():
    assert mercantil._norm("Almería") == "ALMERIA"
    assert mercantil._norm("Álava") == "ALAVA"


def test_seccion_de_identificador():
    assert mercantil._seccion_de("BORME-A-2026-156-01") == "A"
    assert mercantil._seccion_de("BORME-B-2026-156-08") == "B"
    assert mercantil._seccion_de("BORME-C-2026-4727") == "C"
    assert mercantil._seccion_de("cualquiera") == "?"


def test_iter_items_recorre_apartados():
    # Estructura simplificada estilo BORME: seccion A con item[], seccion C con apartado[].item[]
    sumario = {
        "diario": [
            {
                "sumario_diario": {"identificador": "BORME-S-2026-156"},  # sin titulo -> se ignora
                "seccion": [
                    {"codigo": "A", "item": [
                        {"identificador": "BORME-A-2026-156-01", "titulo": "ARABA/ALAVA"},
                    ]},
                    {"codigo": "C", "apartado": [
                        {"codigo": "002", "item": [
                            {"identificador": "BORME-C-2026-4727", "titulo": "ACTIVO MADECO SL"},
                        ]},
                    ]},
                ],
            }
        ]
    }
    items = list(mercantil._iter_items(sumario))
    ids = {it["identificador"] for it in items}
    assert ids == {"BORME-A-2026-156-01", "BORME-C-2026-4727"}  # el BORME-S no aparece


def test_sumario_fecha_invalida():
    assert "no valida" in mercantil.sumario_borme("ayer").lower()


def test_buscar_empresa_vacia():
    out = mercantil.buscar_empresa_mercantil("   ")
    assert "nombre de la sociedad" in out.lower()


def test_buscar_empresa_humano_en_el_bucle():
    out = mercantil.buscar_empresa_mercantil("ACTIVO MADECO SL")
    # No inventa una ficha: ofrece buscadores oficiales y explica el alcance.
    assert mercantil.URL_BUSCADOR_BORME in out
    assert mercantil.URL_RMC in out
    assert "cuentas anuales" in out.lower()
    assert "fe publica" in out.lower()
    assert "ACTIVO MADECO SL" in out


def test_buscar_empresa_detecta_cif():
    out = mercantil.buscar_empresa_mercantil("B12345674")
    assert "CIF" in out


# --------------------------------- red -------------------------------------

@pytest.mark.red
def test_sumario_borme_extrae_items():
    out = mercantil.sumario_borme("14/08/2026")
    assert "BORME-" in out
    assert "entradas" in out


@pytest.mark.red
def test_sumario_borme_filtro_provincia():
    # La Seccion A se agrupa por provincia; 'ALMERIA' debe aparecer ese dia.
    out = mercantil.sumario_borme("2026-08-14", contiene="almeria")
    assert "BORME-A-2026-" in out
