"""Tests offline de la rotacion de IPs (common/rotacion + common/ip_rotator).

Sin red: la descarga con rotacion se prueba con httpx.MockTransport y los
escenarios de activacion con monkeypatch de variables de entorno.
"""

import httpx
import pytest

from common import rotacion
from common.ip_rotator import MAX_POOL_SIZE, PoolFullError, ProxyRotator, parse_proxy


@pytest.fixture(autouse=True)
def _reiniciar(monkeypatch):
    rotacion.reiniciar_para_tests()
    monkeypatch.delenv("IURIS_ROTACION", raising=False)
    monkeypatch.delenv("IURIS_PROXIES", raising=False)
    monkeypatch.delenv("IURIS_ROTACION_MAX", raising=False)
    yield
    rotacion.reiniciar_para_tests()


# --- Libreria vendida: parseo y limite del pool -----------------------------

def test_parse_formatos_de_proxies():
    p = parse_proxy("1.2.3.4:8080")
    assert p.url == "http://1.2.3.4:8080"
    assert p.id == "1.2.3.4:8080"
    p = parse_proxy("1.2.3.4:8080:pepe:secreto")
    assert p.username == "pepe" and p.password == "secreto"
    p = parse_proxy("http://pepe:secreto@5.6.7.8:3128")
    assert p.username == "pepe" and p.port == 3128
    with pytest.raises(ValueError):
        parse_proxy("no-es-un-proxy")


def test_pool_maximo_99():
    rot = ProxyRotator(max_pool_size=MAX_POOL_SIZE)
    for i in range(MAX_POOL_SIZE):
        rot.add(f"10.{i // 256}.{i % 256}.7:{9000 + i}")
    assert len(rot) == MAX_POOL_SIZE == 99
    with pytest.raises(PoolFullError):
        rot.add("10.9.9.9:9999")


def test_auto_recovery_cooldown_y_dead():
    rot = ProxyRotator(["9.9.9.9:1"], cooldown_seconds=60, max_consecutive_failures=2)
    px = rot.next_proxy()
    rot.report_failure(px["id"], "f1")
    assert rot.get(px["id"])["status"] == "cooldown"
    rot.report_failure(px["id"], "f2")
    assert rot.get(px["id"])["status"] == "dead"


# --- Opt-in: apagada por defecto, sin cambiar el comportamiento -------------

def test_apagada_por_defecto():
    assert rotacion.activa() is False
    assert rotacion.max_intentos() == 1
    assert rotacion.proxy_para_navegador() is None
    assert rotacion.linea_estado() is None


def test_activada_con_env_y_fichero(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("10.0.0.1:8080\n# comentario\n10.0.0.2:8080:user:pass\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))
    assert rotacion.activa() is True
    px = rotacion.proxy_para_navegador()
    assert px["server"] in ("http://10.0.0.1:8080", "http://10.0.0.2:8080")
    assert "id" in px
    assert rotacion.max_intentos() == 5  # defecto
    assert rotacion.linea_estado() is not None


def test_max_limitado_a_99(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("10.0.0.1:8080\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))
    monkeypatch.setenv("IURIS_ROTACION_MAX", "500")
    assert rotacion.max_intentos() == MAX_POOL_SIZE


def test_env_sin_fichero_no_activa(monkeypatch, tmp_path):
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(tmp_path / "no-existe.txt"))
    assert rotacion.activa() is False


def test_fichero_vacio_no_activa(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("# solo comentarios\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))
    assert rotacion.activa() is False


# --- Descarga con rotacion (MockTransport, sin red) -------------------------

def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_descarga_rota_en_403_y_exito(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("10.0.0.1:8080\n10.0.0.2:8080\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))

    llamadas = {"n": 0}

    def handler(request):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return httpx.Response(403)
        return httpx.Response(200, content=b"%PDF-1.7 simulado")

    data = await rotacion.descargar_con_rotacion(
        "https://www.poderjudicial.es/x.pdf", transport=_transport(handler)
    )
    assert data is not None and data[:4] == b"%PDF"
    assert llamadas["n"] == 2  # primera IP bloqueada, segunda OK
    # La primera quedo en cooldown y la segunda activa (auto-recovery al dia).
    estados = {p["id"]: p["status"] for p in rotacion._cargar().list()}
    assert sorted(estados.values()) == ["active", "cooldown"]


@pytest.mark.asyncio
async def test_descarga_agota_las_ips(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("10.0.0.1:8080\n10.0.0.2:8080\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))

    llamadas = {"n": 0}

    def handler(request):
        llamadas["n"] += 1
        return httpx.Response(429)

    data = await rotacion.descargar_con_rotacion(
        "https://www.poderjudicial.es/x.pdf", transport=_transport(handler)
    )
    assert data is None
    assert llamadas["n"] == 2  # no insiste mas alla del pool


@pytest.mark.asyncio
async def test_descarga_recurso_no_pdf_no_penaliza_la_ip(monkeypatch, tmp_path):
    f = tmp_path / "proxies.txt"
    f.write_text("10.0.0.1:8080\n", encoding="utf-8")
    monkeypatch.setenv("IURIS_ROTACION", "true")
    monkeypatch.setenv("IURIS_PROXIES", str(f))

    def handler(request):
        return httpx.Response(404, content=b"no encontrado")

    data = await rotacion.descargar_con_rotacion(
        "https://www.poderjudicial.es/no-existe", transport=_transport(handler)
    )
    assert data is None
    estados = {p["status"] for p in rotacion._cargar().list()}
    assert estados == {"active"}  # la IP funciona; el recurso no existe


@pytest.mark.asyncio
async def test_descarga_sin_rotacion_no_hace_nada():
    assert await rotacion.descargar_con_rotacion("https://x/y.pdf") is None
