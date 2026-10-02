"""Guias de escritos: catalogo y busqueda (sin red)."""

from sources import escritos


def test_catalogo_lista_todas():
    out = escritos.guia_escrito("")
    for gid in escritos.GUIAS:
        assert gid in out


def test_busca_por_descripcion_y_jurisdiccion():
    assert escritos._buscar("demanda-despido", "") == ["demanda-despido"]
    assert escritos._buscar("apelacion", "civil") == ["recurso-apelacion-civil"]
    assert escritos._buscar("despido", "laboral") == ["demanda-despido"]


def test_guia_sin_verificar_incluye_masc_en_civil():
    out = escritos.guia_escrito("demanda-juicio-verbal", verificar=False)
    assert "MASC" in out and "15.000" in out and "LEC 250" in out


def test_guia_desconocida_devuelve_catalogo():
    assert "Guias de escritos disponibles" in escritos.guia_escrito("habeas data marciano")


def test_todas_las_guias_tienen_base_legal():
    for g in escritos.GUIAS.values():
        assert g["verificar"] and g["plazos"] and g["estructura"]
