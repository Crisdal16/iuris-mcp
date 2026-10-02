"""Reconocimiento de citas (sin red). Incluye regresiones de la revision de codigo
del 2026-10-02."""

import pytest

from common.citas import clasificar, es_norma_ue, extraer_citas
from sources import boe, ordenanzas, verificacion


def refs(texto):
    return [c.ref for c in extraer_citas(texto)]


def test_escrito_tipico():
    t = ("Conforme al artículo 1902 del Código Civil y a los arts. 394.1 y 398 LEC. "
         "El art. 24 CE. Véase la STS 1177/2014, la STC 31/2010 y ECLI:ES:TS:2014:4786. "
         "Asunto C-311/18. Artículo 3 de la Directiva 93/13/CEE. Artículo 46 de la Ley "
         "29/1998. Consulta V0282-26 y RG 00/06291/2024. El art. 17 RGPD. BOE-A-2000-323.")
    r = refs(t)
    for esperado in ["1902 CC", "394 LEC", "398 LEC", "24 CE", "STS 1177/2014", "STC 31/2010",
                     "ECLI:ES:TS:2014:4786", "C-311/18", "3 Directiva 93/13/CEE",
                     "46 Ley 29/1998", "V0282-26", "00/06291/2024", "17 RGPD", "BOE-A-2000-323"]:
        assert esperado in r, esperado


# --- regresiones -----------------------------------------------------------

def test_punto_de_millar_no_cambia_de_articulo():
    assert refs("artículo 1.902 del Código Civil") == ["1902 CC"]
    assert clasificar("art. 1.902 CC").ref == "1902 CC"
    assert boe._clave_articulo("1.902") == "1902"
    assert boe._clave_articulo("394.1") == "394"


def test_rd_ley_y_decreto_ley_no_son_una_ley():
    c = extraer_citas("El artículo 3 del RD-ley 8/2020 y el artículo 5 del Decreto-ley 1/2021.")
    assert c[0].norma == "RD-ley 8/2020" and not c[0].extra["autonomica"]
    assert boe.parsear_rango_numero("RD-ley 8/2020") == ("RDL", "8/2020")
    assert c[1].norma == "Decreto-ley 1/2021" and c[1].extra["autonomica"]


def test_ley_autonomica_se_marca_y_se_lee_la_fecha():
    c = extraer_citas("El artículo 5 de la Ley 2/2015, de 29 de abril, de empleo público de Galicia.")[0]
    assert c.extra["autonomica"] and c.extra["fecha"] == "29/04"
    c = extraer_citas("El artículo 46 de la Ley 29/1998, de 13 de julio.")[0]
    assert not c.extra["autonomica"] and c.extra["fecha"] == "13/07"


@pytest.mark.parametrize("texto", [
    "El art. 33 regula el recurso de inconstitucionalidad.",
    "El artículo 22 del texto refundido, relativo a la constitución de la sociedad.",
    "El artículo 3 del convenio, conforme al ET, fija la jornada.",
])
def test_sin_normas_fantasma(texto):
    assert [c.norma for c in extraer_citas(texto)] == [""]


def test_enumeraciones_con_normas_distintas():
    r = refs("Según el artículo 18 de la LOPJ y 19 LEC, y el art. 1 de la Ley 39/2015 "
             "y el 2 de la Ley 40/2015.")
    assert r == ["18 LOPJ", "19 LEC", "1 Ley 39/2015", "2 Ley 40/2015"]


def test_plazo_no_es_articulo():
    assert refs("El artículo 7, 15 días después, el ET.") == ["7"]


def test_apartados_y_ordinales():
    assert refs("Artículo 250.1.2º de la LEC.") == ["250 LEC"]
    assert refs("el artículo 6, apartado 1, letra a), del RGPD") == ["6 RGPD"]


def test_asuntos_tjue_solo_con_formato_real():
    assert refs("Anexo C-1/2020 del pliego; asunto C-311/18; expediente c-3/21.") == ["C-311/18"]


def test_reglamentos_espanoles_no_son_ue():
    assert not es_norma_ue("Reglamento Hipotecario")
    assert not es_norma_ue("LEC")
    for ue in ("RGPD", "Reglamento (UE) 2016/679", "Directiva 93/13/CEE", "32016R0679"):
        assert es_norma_ue(ue), ue


def test_fallos_de_las_fuentes_se_detectan():
    for msg in ("TJUE: No hay documento en CELLAR para «C-999/19».",
                "TJUE: ECLI:EU:C:2099:1 sin CELEX.",
                "CELLAR no devolvio texto para 62099CJ0001.",
                "La consulta V9999-99 no devolvio contenido legible.",
                "La pagina https://x no contiene secciones reconocibles."):
        assert verificacion._fallo(msg), msg
    assert not verificacion._fallo("CELEX 62018CJ0311 · Sentencia")


@pytest.mark.parametrize("consulta,esperado", [
    ("inicio de actividad", "ordenanza inicio de actividad"),
    ("prohibición de fumar", "ordenanza prohibición de fumar"),
    ("ICIO", "ordenanza fiscal impuesto construcciones instalaciones obras"),
    ("IBI", "ordenanza fiscal impuesto bienes inmuebles"),
])
def test_materias_de_ordenanzas_por_palabra(consulta, esperado):
    assert ordenanzas._terminos(consulta) == esperado
