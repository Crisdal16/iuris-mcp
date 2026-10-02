"""Lectura por tramos (continuar_lectura): sin red."""

import re

from common import lecturas


def _id(salida: str) -> str:
    return re.search(r"lectura='([0-9a-f]{12})'", salida).group(1)


def test_texto_corto_no_se_recorta():
    assert lecturas.recortar("corto", 100) == "corto"


def test_recorre_el_documento_entero_por_tramos():
    texto = "\n".join(f"Parrafo {i} con algo de texto." for i in range(400))
    primero = lecturas.recortar(texto, 2000, titulo="Doc")
    ident = _id(primero)
    leido = []
    salida = primero
    for _ in range(50):
        cuerpo = salida.split("]\n\n", 1)[1]
        leido.append(cuerpo.split("\n\n[")[0])
        m = re.search(r"desde=(\d+)\)", salida)
        if not m or "Fin del documento" in salida:
            break
        salida = lecturas.tramo(ident, int(m.group(1)), 2000)
    assert "Fin del documento" in salida
    assert "".join(leido) == texto


def test_corta_en_salto_de_linea():
    texto = ("palabra " * 50 + "\n") * 40
    out = lecturas.tramo(lecturas.guardar(texto), 0, 1000)
    cuerpo = out.split("]\n\n", 1)[1].split("\n\n[…")[0]
    assert not cuerpo.endswith("palab")


def test_lectura_inexistente_y_fuera_de_rango():
    assert "No encuentro" in lecturas.tramo("000000000000")
    ident = lecturas.guardar("hola mundo")
    assert "no hay nada" in lecturas.tramo(ident, 500)
