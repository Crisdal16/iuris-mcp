"""Tests de parseo de identificadores.

Los valores esperados NO son inventados: se verificaron contra el CENDOJ
(a traves del conector Jurisprudenciator) durante el diseno. Sirven de oraculo.
"""

import pytest

from common.cendoj_ids import (
    Roj,
    normalizar_cita,
    parse_ecli,
    parse_id_cendoj,
    parse_roj,
    roj_a_ecli,
    separar_citas,
)
from common.organos import (
    ORGANOS,
    codigos_por_jurisdiccion,
    codigos_por_tipo_organo,
    sigla_provincia,
)


# ---------------------------------------------------------------------------
# ECLI
# ---------------------------------------------------------------------------

def test_ecli_sentencia_ts():
    e = parse_ecli("ECLI:ES:TS:2014:1177")
    assert (e.pais, e.tribunal, e.anio, e.numero) == ("ES", "TS", 2014, "1177")
    assert e.es_auto is False
    assert str(e) == "ECLI:ES:TS:2014:1177"


def test_ecli_auto_conserva_la_A():
    """Regla critica: la 'A' final distingue el auto de la sentencia homonima."""
    e = parse_ecli("ECLI:ES:APB:2019:9672A")
    assert e.es_auto is True
    assert e.tribunal == "APB"
    assert str(e) == "ECLI:ES:APB:2019:9672A"


def test_ecli_sentencia_y_auto_no_se_confunden():
    sentencia = parse_ecli("ECLI:ES:APB:2019:9672")
    auto = parse_ecli("ECLI:ES:APB:2019:9672A")
    assert sentencia.numero == auto.numero
    assert sentencia.es_auto != auto.es_auto
    assert str(sentencia) != str(auto)


def test_ecli_tjue():
    e = parse_ecli("ECLI:EU:C:2020:559")
    assert e.pais == "EU" and e.tribunal == "C"


def test_ecli_invalido():
    assert parse_ecli("no es un ecli") is None


# ---------------------------------------------------------------------------
# ROJ
# ---------------------------------------------------------------------------

def test_roj_ts_sin_provincia():
    r = parse_roj("STS 1177/2014")
    assert (r.clase, r.organo, r.provincia, r.numero, r.anio) == (
        "S", "TS", None, "1177", 2014)
    assert r.es_auto is False


def test_roj_ap_con_provincia():
    r = parse_roj("SAP VA 863/2026")
    assert (r.organo, r.provincia, r.numero, r.anio) == ("AP", "VA", "863", 2026)


def test_roj_auto():
    r = parse_roj("AAP B 9672/2019")
    assert r.clase == "A" and r.es_auto is True
    assert r.provincia == "B"


def test_roj_tsj():
    r = parse_roj("STSJ M 971/2012")
    assert r.organo == "TSJ" and r.provincia == "M"


def test_roj_roundtrip_str():
    assert str(parse_roj("SAP VA 863/2026")) == "SAP VA 863/2026"


# ---------------------------------------------------------------------------
# ROJ -> ECLI (valores verificados contra el CENDOJ)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("roj_txt,ecli_txt", [
    ("STS 1177/2014", "ECLI:ES:TS:2014:1177"),
    ("SAP VA 863/2026", "ECLI:ES:APVA:2026:863"),
    ("AAP B 9672/2019", "ECLI:ES:APB:2019:9672A"),
    ("STSJ M 971/2012", "ECLI:ES:TSJM:2012:971"),
])
def test_roj_a_ecli(roj_txt, ecli_txt):
    assert str(roj_a_ecli(parse_roj(roj_txt))) == ecli_txt


def test_roj_a_ecli_auto_marca_la_A():
    assert str(roj_a_ecli(parse_roj("AAP B 9672/2019"))).endswith("A")
    assert not str(roj_a_ecli(parse_roj("SAP B 9672/2019"))).endswith("A")


def test_roj_ap_sin_provincia_no_resuelve():
    """Una AP sin provincia no puede formar ECLI: mejor None que adivinar."""
    assert roj_a_ecli(Roj("S", "AP", None, "863", 2026)) is None


# ---------------------------------------------------------------------------
# Id Cendoj  (28079 14 001 2014 100117)
# ---------------------------------------------------------------------------

def test_id_cendoj_descompone():
    i = parse_id_cendoj("28079140012014100117")
    assert i.municipio == "28079"      # Madrid
    assert i.organo == "14"            # TS Sala de lo Social
    assert i.seccion == "001"
    assert i.anio == 2014
    assert i.serial == "100117"


def test_id_cendoj_organo_coincide_con_la_tabla():
    i = parse_id_cendoj("28079140012014100117")
    assert i.descripcion_organo == ORGANOS["14"]
    assert "SOCIAL" in i.descripcion_organo


def test_id_cendoj_longitud_incorrecta():
    assert parse_id_cendoj("123") is None


# ---------------------------------------------------------------------------
# Normalizacion y troceado
# ---------------------------------------------------------------------------

def test_normalizar_detecta_cada_tipo():
    assert parse_ecli(str(normalizar_cita("ECLI:ES:TS:2014:1177")))
    assert isinstance(normalizar_cita("STS 1177/2014"), Roj)
    assert normalizar_cita("28079140012014100117").organo == "14"
    assert normalizar_cita("C-311/19") == "C-311/19"
    assert normalizar_cita("cualquier cosa") is None


def test_separar_citas_respeta_espacios_internos():
    """Un ROJ lleva espacios ('SAP VA 863/2026'): no vale partir por espacios."""
    citas = separar_citas("STS 1177/2014, SAP VA 863/2026")
    assert citas == ["STS 1177/2014", "SAP VA 863/2026"]


# ---------------------------------------------------------------------------
# Tablas de organos
# ---------------------------------------------------------------------------

def test_hay_38_organos():
    assert len(ORGANOS) == 38


def test_alias_tipo_organo():
    assert codigos_por_tipo_organo("AP") == ["37", "38"]
    assert "14" in codigos_por_tipo_organo("TS")
    assert codigos_por_tipo_organo("37") == ["37"]   # codigo literal
    assert codigos_por_tipo_organo("inventado") == []


def test_jurisdiccion():
    assert "14" in codigos_por_jurisdiccion("SOCIAL")
    assert "12" in codigos_por_jurisdiccion("penal")   # sin distinguir mayusculas


def test_sigla_provincia():
    assert sigla_provincia("Valladolid") == "VA"
    assert sigla_provincia("Barcelona") == "B"
    assert sigla_provincia("A Coruña") == "C"          # con tilde/enye
    assert sigla_provincia("VA") == "VA"               # ya es sigla
    assert sigla_provincia("Narnia") is None


# ---------------------------------------------------------------------------
# Alias: nombre de provincia / comunidad en el ROJ (fix descargas 2026-11)
# ---------------------------------------------------------------------------

def test_roj_acepta_nombre_comunidad():
    r = parse_roj("STSJ Murcia 1791/2025")
    assert r is not None
    assert (r.clase, r.organo, r.provincia, r.numero, r.anio) == ("S", "TSJ", "MU", "1791", 2025)
    assert str(r) == "STSJ MU 1791/2025"      # se normaliza a la sigla oficial


def test_roj_nombre_comunidad_ecli():
    e = roj_a_ecli(parse_roj("STSJ Murcia 1791/2025"))
    assert str(e) == "ECLI:ES:TSJMU:2025:1791"


def test_roj_nombres_de_provincia():
    assert parse_roj("SAP Valladolid 863/2026").provincia == "VA"
    assert parse_roj("SAP Barcelona 123/2024").provincia == "B"
    assert parse_roj("STS Tenerife 5/2024").provincia == "TF"   # TS la ignora en ECLI
    assert parse_roj("AAP Sevilla 77/2023").provincia == "SE"


def test_roj_comunidades_con_sede_unica():
    assert parse_roj("STSJ Catalunya 10/2024").provincia == "B"
    assert parse_roj("STSJ Euskadi 10/2024").provincia == "BI"
    assert parse_roj("STSJ Madrid 10/2024").provincia == "M"


def test_roj_nombre_desconocido_no_inventa_sigla():
    assert parse_roj("STSJ Narnia 5/2024") is None
    assert parse_roj("STSJ Atenas 5/2024") is None


def test_sigla_roj_helper():
    from common.cendoj_ids import sigla_roj
    assert sigla_roj("Murcia") == "MU"
    assert sigla_roj("cataluña") == "B"      # sin distinguir mayusculas ni tildes
    assert sigla_roj("VA") == "VA"
    assert sigla_roj("Narnia") is None
    assert sigla_roj("") is None


def test_citas_extrae_roj_con_nombre_comunidad():
    from common.citas import extraer_citas
    ts = extraer_citas("Conforme a la STSJ Murcia 1791/2025 y a la SAP VA 863/2026.")
    rojs = [c.ref for c in ts if c.tipo == "cendoj"]
    assert "STSJ MU 1791/2025" in rojs
    assert "SAP VA 863/2026" in rojs


def test_normalizar_cita_regresion_siglas():
    # lo que ya funcionaba debe seguir funcionando
    assert str(parse_roj("STSJ MU 1791/2025")) == "STSJ MU 1791/2025"
    assert str(parse_roj("STS 1177/2014")) == "STS 1177/2014"
    assert str(parse_roj("SAP VA 863/2026")) == "SAP VA 863/2026"
    assert parse_roj("ATS 12/2020").numero == "12"
