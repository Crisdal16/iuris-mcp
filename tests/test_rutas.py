"""Validacion de rutas que llegan del modelo (guardar resoluciones / leer escritos)."""

import os

import pytest

from common.texto import dir_destino, ruta_permitida


def test_sin_raiz_admite_rutas_locales(tmp_path, monkeypatch):
    monkeypatch.delenv("IURIS_RAIZ", raising=False)
    assert ruta_permitida(str(tmp_path)) == os.path.realpath(str(tmp_path))


def test_rechaza_bytes_nulos_y_unc(monkeypatch):
    monkeypatch.delenv("IURIS_RAIZ", raising=False)
    with pytest.raises(ValueError):
        ruta_permitida("C:/tmp/a\x00b")
    if os.name == "nt":
        with pytest.raises(ValueError):
            ruta_permitida("\\\\servidor\\recurso\\x")
    with pytest.raises(ValueError):
        ruta_permitida("//servidor/recurso/x")


def test_con_raiz_solo_dentro(tmp_path, monkeypatch):
    raiz = tmp_path / "expedientes"
    raiz.mkdir()
    monkeypatch.setenv("IURIS_RAIZ", str(raiz))
    assert ruta_permitida(str(raiz / "cliente1")).startswith(os.path.realpath(str(raiz)))
    with pytest.raises(ValueError):
        ruta_permitida(str(tmp_path / "otra"))
    with pytest.raises(ValueError):   # escapar con ..
        ruta_permitida(str(raiz / ".." / "otra"))


def test_dir_destino_crea_dentro_de_la_raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("IURIS_RAIZ", str(tmp_path))
    d = dir_destino(str(tmp_path / "exp" / "2026"), str(tmp_path / "defecto"))
    assert os.path.isdir(d)
    with pytest.raises(ValueError):
        dir_destino(os.path.expanduser("~"), str(tmp_path / "defecto"))
