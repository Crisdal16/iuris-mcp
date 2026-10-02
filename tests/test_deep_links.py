"""Tests de los enlaces 'humano en el bucle' (UE/TC/TJUE). Todo offline."""

import pytest

from sources import deep_links as dl


@pytest.mark.parametrize("ref,celex", [
    ("RGPD", "32016R0679"),
    ("gdpr", "32016R0679"),
    ("Directiva 93/13/CEE", "31993L0013"),
    ("Reglamento (UE) 2016/679", "32016R0679"),
    ("32016R0679", "32016R0679"),
    ("Reglamento de IA", "32024R1689"),
    ("Decision 2002/584/JAI", "32002D0584"),
])
def test_a_celex(ref, celex):
    assert dl.a_celex(ref) == celex


def test_a_celex_desconocido():
    assert dl.a_celex("una cosa cualquiera") is None


def test_norma_ue_da_url_eurlex():
    out = dl.norma_ue("RGPD", "17")
    assert "eur-lex.europa.eu" in out
    assert "32016R0679" in out


def test_norma_ue_no_convertible():
    assert "No supe convertir" in dl.norma_ue("xyz")


def test_tc_y_tjue_dan_enlace():
    assert "tribunalconstitucional" in dl.tc_buscar("amparo")
    assert "curia.europa.eu" in dl.tjue_buscar("C-311/19")
