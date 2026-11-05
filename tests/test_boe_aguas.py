"""buscar_articulo sobre el TRLA y el RDPH (expedientes de la CHS).

Regresion del fallo visto el 2026-09-20: el art. 117 TRLA y el 315 RDPH salian
con la redaccion ORIGINAL (2001 / 1986, importes en pesetas) como si fuera la
vigente, porque se tomaba la primera <version> del bloque. Las respuestas del
BOE estan grabadas en tests/fixtures (bloques a117 y a315, descargados el
2026-11-05 de la API de datos abiertos), asi que estas pruebas no usan la red.
La ultima (marcada 'red') consulta el BOE en vivo.
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from common import citas
from sources import boe

FIX = Path(__file__).parent / "fixtures"

CASOS = [
    # norma, bloque, sigla, articulo, vigente desde, norma que da la redaccion vigente
    ("BOE-A-2001-14276", "a117", "TRLA", "117", "21/12/2012", "BOE-A-2012-15337"),
    ("BOE-A-1986-10638", "a315", "RDPH", "315", "24/10/2024", "BOE-A-2024-21701"),
]


def _xml(norma: str, bloque: str) -> str:
    return (FIX / f"boe_{norma}_{bloque}.xml").read_text(encoding="utf-8")


def _texto(v) -> str:
    return "".join(v.itertext()).lower()


# ------------------------------- siglas -------------------------------------

@pytest.mark.parametrize("ley,esperado", [
    ("TRLA", "BOE-A-2001-14276"),
    ("trla", "BOE-A-2001-14276"),
    ("Ley de Aguas", "BOE-A-2001-14276"),
    ("Texto Refundido de la Ley de Aguas", "BOE-A-2001-14276"),
    ("RDPH", "BOE-A-1986-10638"),
    ("Reglamento del Dominio Público Hidráulico", "BOE-A-1986-10638"),
])
def test_resolver_siglas_aguas(ley, esperado):
    assert boe.resolver_norma(ley, red=False) == esperado


@pytest.mark.parametrize("frase,sigla", [
    ("conforme al art. 117 TRLA", "TRLA"),
    ("tipificada en el artículo 315 c) del RDPH", "RDPH"),
])
def test_verificar_escrito_reconoce_trla_y_rdph(frase, sigla):
    arts = [c for c in citas.extraer_citas(frase) if c.tipo == "articulo"]
    assert arts and arts[0].norma.upper() == sigla


# ------------------------- fixture grabada del BOE ---------------------------

@pytest.mark.parametrize("norma,bloque,sigla,art,desde,modif", CASOS)
def test_la_fixture_trae_la_original_en_pesetas(norma, bloque, sigla, art, desde, modif):
    """La primera <version> es la original en pesetas: es lo que servia el fallo."""
    versiones = ET.fromstring(_xml(norma, bloque)).findall(".//version")
    assert len(versiones) > 1
    assert versiones[0].get("id_norma") == norma
    assert "pesetas" in _texto(versiones[0])


@pytest.mark.parametrize("norma,bloque,sigla,art,desde,modif", CASOS)
def test_sirve_la_version_de_fecha_vigencia_mas_reciente(norma, bloque, sigla, art, desde, modif):
    versiones = ET.fromstring(_xml(norma, bloque)).findall(".//version")
    ultima = max(versiones, key=lambda v: v.get("fecha_vigencia"))
    actual, futura = boe.elegir_version(versiones, hoy="20261105")
    assert actual is ultima
    assert actual.get("id_norma") == modif
    assert futura is None


@pytest.mark.parametrize("norma,bloque,sigla,art,desde,modif", CASOS)
def test_buscar_articulo_devuelve_el_consolidado(monkeypatch, norma, bloque, sigla, art, desde, modif):
    """buscar_articulo de punta a punta, con el indice y el bloque del BOE simulados."""
    pedidas: list[str] = []

    def fake_json(url, **kw):
        pedidas.append(url)
        assert url.endswith(f"/legislacion-consolidada/id/{norma}/texto/indice")
        return {"data": [{"bloque": [
            {"id": "a1", "titulo": "Artículo 1"},
            {"id": bloque, "titulo": f"Artículo {art}"},
        ]}]}

    def fake_xml(url, **kw):
        pedidas.append(url)
        assert url.endswith(f"/legislacion-consolidada/id/{norma}/texto/bloque/{bloque}")
        return _xml(norma, bloque)

    monkeypatch.setattr(boe, "get_json", fake_json)
    monkeypatch.setattr(boe, "get_xml", fake_xml)

    r = boe.buscar_articulo(sigla, art)
    assert len(pedidas) == 2, "no debe leer el texto del indice ni del diario original"
    assert "pesetas" not in r.lower()
    assert "euros" in r.lower()
    assert f"vigente desde {desde}" in r
    assert f"redaccion vigente dada por {modif}" in r


# -------------------------------- en vivo -----------------------------------

@pytest.mark.red
@pytest.mark.parametrize("norma,bloque,sigla,art,desde,modif", CASOS)
def test_en_vivo_trla_117_y_rdph_315(norma, bloque, sigla, art, desde, modif):
    r = boe.buscar_articulo(sigla, art)
    assert f"Artículo {art}" in r
    assert "pesetas" not in r.lower()
    assert "euros" in r.lower()
    assert "vigente desde" in r and "redaccion vigente dada por" in r
