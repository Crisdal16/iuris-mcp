"""Tests del modulo FISCAL (DGT + TEAC/TEAR).

  - Offline (siempre): normalizacion de fechas, parseo de numeros (consulta y
    RG), mapeo de organos y parseo de fragmentos HTML de ejemplo.
  - Red (marcados 'red'): golpean los buscadores oficiales de Hacienda
    (PETETE para la DGT, DYCTEA para el TEAC). Se saltan con  -m "not red".
"""

import pytest

from sources import dgt, teac


# ------------------------------- DGT: offline ------------------------------

def test_dgt_fecha_es():
    assert dgt._fecha_es("2026-02-09") == "09/02/2026"
    assert dgt._fecha_es("09/02/2026") == "09/02/2026"
    assert dgt._fecha_es("") == ""
    assert dgt._fecha_es("ayer") == ""


def test_dgt_params_omite_vacios():
    # Los campos vacios NO deben viajar (cuelgan el motor KNOSYS con timeout).
    p = dgt._params_busqueda("", "V0282-26", "", "", "", "2", 1)
    assert p["VLCMP_1"] == "V0282-26"
    assert "VLCMP_6" not in p
    assert p["tab"] == "2" and p["page"] == "1"


def test_dgt_numero_invalido():
    out = dgt.leer_consulta_hacienda("no-soy-un-numero")
    assert "no parece un numero" in out


def test_dgt_sin_criterios():
    out = dgt.buscar_consultas_hacienda()
    assert "Indica al menos un criterio" in out
    assert dgt.BUSCADOR_URL in out


def test_dgt_parsear_resultados():
    frag = '''<div><script>updateNumResults("2", "3");</script>
      <table class="results"><tbody><tr>
      <td id="doc_74271" onClick="return viewDocument(74271, 2);">
        <h4><span class="NUM-CONSULTA"><strong> V0282-26 </strong></span></h4>
        <span class="DESCRIPCION-HECHOS"> Entidad de formacion online. </span>
        <span class="CUESTION-PLANTEADA"><i> Exencion de IVA. </i></span>
      </td></tr></tbody></table></div>'''
    assert dgt._extraer_total(frag) == 3
    filas = dgt._parsear_resultados(frag)
    assert len(filas) == 1
    assert filas[0]["numero"] == "V0282-26"
    assert filas[0]["doc"] == "74271" and filas[0]["tab"] == "2"
    assert "IVA" in filas[0]["cuestion"]


# ------------------------------ TEAC: offline ------------------------------

def test_teac_partir_rg():
    assert teac._partir_rg("00/06291/2024") == ("00", "06291", "2024")
    assert teac._partir_rg("06291/2024") == ("00", "06291", "2024")
    assert teac._partir_rg("nada") is None


def test_teac_codigo_organo():
    assert teac._codigo_organo("TEAC") == "00"
    assert teac._codigo_organo("TEAR Murcia") == "29"
    assert teac._codigo_organo("Murcia") == "29"
    assert teac._codigo_organo("Cataluña") == "24"
    assert teac._codigo_organo("Marte") == ""


def test_teac_sin_criterios():
    out = teac.buscar_doctrina_teac()
    assert "Indica al menos texto" in out


def test_teac_rg_invalido():
    assert "no parece un numero" in teac.leer_resolucion_teac("xxx")


def test_teac_parsear_lista():
    html = '''<div>7 resultados. <ul>
      <li class='resultadoCriterio'>
        <span class='resultadoCriterioTitulo'>
          <a href='criterio.aspx?id=00/06291/2024/00/0/1&amp;q=x'>
          Criterio 1 de la resolución 00/06291/2024/00/00 del 23/01/2026 - TEAC</a>
        </span>
        <span class='resultadoCriterioTexto'>Procedimiento de gestion. Caducidad.</span>
      </li></ul></div>'''
    total, filas = teac._parsear_lista(html)
    assert total == 7
    assert len(filas) == 1
    assert filas[0]["id"] == "00/06291/2024/00/0/1"
    assert filas[0]["rg"] == "00/06291/2024"
    assert "Caducidad" in filas[0]["asunto"]


# --------------------------------- red -------------------------------------

@pytest.mark.red
def test_dgt_buscar_exencion_iva():
    out = dgt.buscar_consultas_hacienda("exención IVA enseñanza", limite=5)
    assert "Vinculantes" in out
    assert "resultados" in out
    assert "V" in out  # al menos un numero de consulta tipo Vxxxx-xx


@pytest.mark.red
def test_dgt_leer_consulta_v0282_26():
    out = dgt.leer_consulta_hacienda("V0282-26")
    assert "V0282-26" in out
    assert "Cuestion planteada" in out or "Cuestión planteada" in out
    assert "37/1992" in out  # normativa (Ley del IVA)


@pytest.mark.red
def test_teac_buscar_comprobacion_valores():
    out = teac.buscar_doctrina_teac(consulta="comprobación de valores", maximo=5)
    assert "resultados" in out
    assert "resolución" in out or "resolucion" in out


@pytest.mark.red
def test_teac_leer_resolucion():
    out = teac.leer_resolucion_teac("00/06291/2024")
    assert "06291/2024" in out
    assert "TEAC" in out
    assert "textoresolucion.aspx" in out
