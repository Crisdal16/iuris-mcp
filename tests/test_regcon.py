"""Tests del modulo REGCON (convenios colectivos).

Offline (siempre): normalizacion, resolucion de territorio/ambito, deteccion de
BOE-A y de codigo de 14 digitos, recorte de articulos y mensajes de guia.

Red (marcados 'red'): leen la publicacion real del convenio en el BOE. Se saltan
con  pytest -m "not red".  Oraculo: ALEH VI = BOE-A-2023-6344 (codigo REGCON
99010365011900), verificado contra la publicacion oficial del BOE.
"""

import pytest

from sources import regcon


# ------------------------------- offline -----------------------------------

def test_norm_sin_tildes():
    assert regcon._norm("Hostelería") == "HOSTELERIA"
    assert regcon._norm("A Coruña") == "A CORUNA"


def test_resolver_territorio_provincia():
    assert regcon.resolver_territorio("Madrid")[0] == "28"
    assert regcon.resolver_territorio("madrid")[0] == "28"


def test_resolver_territorio_ccaa_y_estatal():
    assert regcon.resolver_territorio("Cataluña")[0] == "58"
    assert regcon.resolver_territorio("estatal")[0] == "63"


def test_resolver_territorio_laxo():
    # 'Comunidad de Madrid' debe caer en Madrid (28).
    assert regcon.resolver_territorio("Comunidad de Madrid")[0] == "28"


def test_resolver_territorio_desconocido():
    assert regcon.resolver_territorio("Narnia") is None


def test_resolver_ambito_por_defecto_sector():
    assert regcon.resolver_ambito("sector") == ("6", "SECTOR IGUAL O SUPERIOR A LA PROVINCIA")
    assert regcon.resolver_ambito("")[0] == "6"
    assert regcon.resolver_ambito("empresa")[0] == "3"


def test_boe_id_detecta():
    assert regcon._boe_id("texto BOE-A-2023-6344 mas texto") == "BOE-A-2023-6344"
    assert regcon._boe_id("", "boe-a-2019-4645").startswith("BOE-A-2019")
    assert regcon._boe_id("hosteleria") is None


def test_recortar_articulo():
    lineas = [
        "Preambulo bla",
        "Artículo 3. Ámbito personal.",
        "El presente acuerdo afecta a...",
        "Artículo 4. Ámbito temporal.",
        "Vigencia...",
    ]
    bloque = regcon._recortar_articulo(lineas, "3")
    assert "Ámbito personal" in bloque
    assert "Ámbito temporal" not in bloque


def test_buscar_convenio_humano_en_el_bucle():
    out = regcon.buscar_convenio("hosteleria", "Madrid")
    assert regcon.REGCON_CONSULTA_PUBLICA in out
    assert "Madrid" in out
    assert "SECTOR" in out


def test_buscar_convenio_con_boe_id_redirige_a_lectura():
    out = regcon.buscar_convenio("BOE-A-2023-6344")
    assert "leer_convenio" in out
    assert "BOE-A-2023-6344" in out


def test_leer_convenio_sin_boe_id_pide_referencia():
    out = regcon.leer_convenio(consulta="el metal", territorio="Madrid")
    assert "BOE-A" in out
    assert "buscar_convenio" in out


def test_leer_convenio_codigo14_orienta_a_regcon():
    out = regcon.leer_convenio(codigo="99010365011900")
    assert "14 digitos" in out
    assert regcon.REGCON_CONSULTA_PUBLICA in out


def test_vigencia_convenio_orienta_a_regcon():
    out = regcon.vigencia_convenio("99010365011900")
    assert regcon.REGCON_CONSULTA_PUBLICA in out
    assert "DENUNCIADO" in out


def test_vigencia_convenio_con_boe_id_enlaza_boe():
    out = regcon.vigencia_convenio("BOE-A-2023-6344")
    assert "BOE-A-2023-6344" in out


# --------------------------------- red -------------------------------------

@pytest.mark.red
def test_leer_convenio_aleh_vi_texto():
    """Oraculo: ALEH VI trae su codigo REGCON y menciona Hosteleria."""
    out = regcon.leer_convenio(codigo="BOE-A-2023-6344")
    assert "Hostelería" in out
    assert "99010365011900" in out  # codigo de convenio de 14 digitos
    assert "BOE-A-2023-6344" in out


@pytest.mark.red
def test_leer_convenio_articulo_concreto():
    """El articulo 3 del ALEH VI es 'Ámbito personal'."""
    out = regcon.leer_convenio(codigo="BOE-A-2023-6344", articulo="3")
    assert "Ámbito personal" in out
    # No debe volcarse el acuerdo entero al pedir un solo articulo.
    assert len(out) < 6000
