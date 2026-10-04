"""Test de humo (con red) de los selectores del CENDOJ.

cendoj_live rellena el formulario del CENDOJ con selectores CSS y, por diseno,
sigue adelante si un control no aparece. Si el sitio cambia, la busqueda "funciona"
pero sin el filtro (bug real de 2026-10-02: jurisdiccion='Penal' devolvia STS
civiles porque se buscaba un boton que no existia). Este test falla en voz alta
en cuanto desaparece cualquier selector del que depende el modulo.

Coste: una carga del formulario y UNA busqueda de un resultado. No es un barrido.
"""

import asyncio

import pytest

from sources.cendoj_live import (
    _JURISDICCION_LABEL,
    _PROVINCIA_A_CCAA,
    BASE_FORM,
    CendojBrowser,
)

pytestmark = pytest.mark.red

# Selectores que buscar() usa en el formulario.
FORMULARIO = [
    "input#frmBusquedajurisprudencia_TEXT",
    "input#frmBusquedajurisprudencia_ROJ",
    "input#frmBusquedajurisprudencia_ECLI",
    "input#frmBusquedajurisprudencia_NUMERORESOLUCION",
    "input#frmBusquedajurisprudencia_NUMERORECURSO",
    "input#frmBusquedajurisprudencia_PONENTE",
    "input#frmBusquedajurisprudencia_NORMA",
    "input#frmBusquedajurisprudencia_FECHARESOLUCIONDESDE",
    "input#frmBusquedajurisprudencia_FECHARESOLUCIONHASTA",
    "select#frmBusquedajurisprudencia_JURISDICCION",
    "button#COMUNIDADmultiselec",
    "button#srcjur_search",
]

# Selectores de la pagina de resultados (orden, por pagina, tarjetas).
RESULTADOS = [
    "select#frmFilterjurisprudencia_cboresults",
    "select#frmFilterjurisprudencia_cbosort",
    "div#jurisprudenciaresults_searchresults div.searchresult",
    'div#jurisprudenciaresults_searchresults a[id^="ref-"]',
    "div#jurisprudenciaresults_searchresults div.metadatos",
]


async def _faltan(page, selectores):
    return [s for s in selectores if not await page.locator(s).count()]


async def _inspeccionar_formulario():
    async with CendojBrowser() as br:
        p = br.page
        await p.goto(BASE_FORM, timeout=30000)
        await p.wait_for_load_state("networkidle")
        await br._cerrar_modal()
        faltan = await _faltan(p, FORMULARIO)
        opciones = await p.evaluate(
            "() => { const s = document.querySelector("
            "'select#frmBusquedajurisprudencia_JURISDICCION');"
            " return s ? [...s.options].map(o => o.value) : []; }"
        )
        # textContent, no innerText: el panel esta cerrado (oculto).
        comunidades = await p.evaluate(
            "() => [...document.querySelectorAll('ul#COMUNIDADpanel > li')]"
            ".map(li => li.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean)"
        )
        return faltan, opciones, comunidades


async def _inspeccionar_resultados():
    async with CendojBrowser() as br:
        await br.buscar(roj="STS", fecha_desde="2026-01-01", fecha_hasta="2026-01-31")
        p = br.page
        faltan = await _faltan(p, RESULTADOS)
        paginar = await p.evaluate("() => typeof goToPage === 'function'")
        return faltan, paginar


@pytest.fixture(scope="module")
def formulario():
    return asyncio.run(_inspeccionar_formulario())


def test_selectores_del_formulario(formulario):
    faltan, _, _ = formulario
    assert not faltan, f"El CENDOJ ya no tiene estos controles: {faltan}"


def test_valores_de_jurisdiccion_existen(formulario):
    _, opciones, _ = formulario
    nuestros = set(_JURISDICCION_LABEL.values())
    assert nuestros <= set(opciones), (
        f"Valores de jurisdiccion que el formulario ya no ofrece: {nuestros - set(opciones)}"
    )


def test_comunidades_autonomas_existen(formulario):
    _, _, comunidades = formulario
    # has-text de Playwright no distingue mayusculas: se compara igual.
    texto = " | ".join(comunidades).upper()
    ausentes = sorted({c for c in _PROVINCIA_A_CCAA.values() if c.upper() not in texto})
    assert not ausentes, f"CCAA que no aparecen en el filtro de localizacion: {ausentes}"


def test_selectores_de_resultados():
    faltan, paginar = asyncio.run(_inspeccionar_resultados())
    assert not faltan, f"La pagina de resultados ya no tiene: {faltan}"
    assert paginar, "La funcion global goToPage() ya no existe (paginacion rota)"
