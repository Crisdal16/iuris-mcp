"""Modo remoto (HTTP): token obligatorio, 401/200, perfil de tools y limite. Sin red."""

import pytest
from mcp.server import MCPServer
from starlette.testclient import TestClient

from common import remoto
from common.texto import dir_destino, ruta_permitida

TOKEN = "t" * 40
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "test", "version": "0"}},
}
CABECERAS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _servidor() -> MCPServer:
    s = MCPServer(name="prueba")

    @s.tool()
    def uno() -> str:
        return "1"

    @s.tool()
    def dos() -> str:
        return "2"

    return s


def _cliente(**kw):
    cfg = remoto.ConfigHTTP(tokens=[TOKEN], **kw)
    return TestClient(remoto.crear_app(_servidor(), cfg), base_url="http://127.0.0.1:8790")


# --- configuracion ---------------------------------------------------------

def test_sin_token_no_arranca():
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.config_desde_entorno(env={})
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.config_desde_entorno(env={"IURIS_HTTP_TOKEN": "  ,  "})


def test_token_corto_no_arranca():
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.config_desde_entorno(env={"IURIS_HTTP_TOKEN": "corto"})


def test_main_http_sin_token_sale_con_error(monkeypatch):
    import server

    monkeypatch.delenv("IURIS_HTTP_TOKEN", raising=False)
    with pytest.raises(SystemExit) as e:
        server.main(["--http"])
    assert e.value.code == 2


def test_config_por_defecto_y_argumentos():
    cfg = remoto.config_desde_entorno(env={"IURIS_HTTP_TOKEN": TOKEN})
    assert (cfg.host, cfg.port, cfg.path, cfg.tools, cfg.rpm) == ("127.0.0.1", 8790, "/mcp", "auditor", 60)
    cfg = remoto.config_desde_entorno(env={"IURIS_HTTP_TOKEN": TOKEN, "IURIS_HTTP_PORT": "9000",
                                           "IURIS_ALLOWED_HOSTS": "iuris.ejemplo.es"},
                                      port=9100, tools="todas")
    assert cfg.port == 9100 and cfg.tools == "todas" and cfg.allowed_hosts == ["iuris.ejemplo.es"]


# --- autenticacion ---------------------------------------------------------

def test_401_sin_cabecera_y_con_token_malo():
    with _cliente() as c:
        r = c.post("/mcp", json=INIT, headers=CABECERAS)
        assert r.status_code == 401
        assert r.headers["www-authenticate"].lower().startswith("bearer")
        r = c.post("/mcp", json=INIT, headers={**CABECERAS, "Authorization": "Bearer " + "x" * 40})
        assert r.status_code == 401
        r = c.post("/mcp", json=INIT, headers={**CABECERAS, "Authorization": "Basic " + TOKEN})
        assert r.status_code == 401


def test_200_con_token():
    with _cliente() as c:
        r = c.post("/mcp", json=INIT, headers={**CABECERAS, "Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "prueba"


def test_salud_sin_token():
    with _cliente() as c:
        assert c.get("/salud").status_code == 200


def test_host_no_declarado_rechazado():
    cfg = remoto.ConfigHTTP(tokens=[TOKEN])
    with TestClient(remoto.crear_app(_servidor(), cfg), base_url="http://malo.ejemplo") as c:
        r = c.post("/mcp", json=INIT, headers={**CABECERAS, "Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 421


def test_limite_por_minuto():
    with _cliente(rpm=2) as c:
        h = {**CABECERAS, "Authorization": f"Bearer {TOKEN}"}
        assert c.post("/mcp", json=INIT, headers=h).status_code == 200
        assert c.post("/mcp", json=INIT, headers=h).status_code == 200
        r = c.post("/mcp", json=INIT, headers=h)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_ventana_deslizante():
    t = [0.0]
    lim = remoto.LimitePorMinuto(1, reloj=lambda: t[0])
    assert lim.permitir(0)[0]
    assert not lim.permitir(0)[0]
    assert lim.permitir(1)[0]  # otro token, otra cuenta
    t[0] = 61
    assert lim.permitir(0)[0]


# --- perfil de herramientas ------------------------------------------------

def test_perfil_lista_y_todas():
    s = _servidor()
    assert remoto.aplicar_perfil(s, "uno") == ["uno"]
    assert [t.name for t in s._tool_manager.list_tools()] == ["uno"]
    assert remoto.aplicar_perfil(_servidor(), "todas") == ["dos", "uno"]
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.aplicar_perfil(_servidor(), "uno,inexistente")


def test_perfil_auditor_existe_en_el_servidor_real():
    import server

    nombres = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert set(remoto.PERFIL_AUDITOR) <= nombres
    assert "buscar_sentencias" not in remoto.PERFIL_AUDITOR  # navegador: fuera en remoto


# --- disco vedado en remoto ------------------------------------------------

def test_sin_disco_en_remoto(tmp_path, monkeypatch):
    monkeypatch.setenv("IURIS_SIN_DISCO", "1")
    with pytest.raises(ValueError):
        ruta_permitida(str(tmp_path / "escrito.docx"))
    with pytest.raises(ValueError):
        dir_destino("", str(tmp_path))


# --- CENDOJ vedado en remoto (aviso legal: no uso comercial) ---------------

def _servidor_con_cendoj() -> MCPServer:
    s = _servidor()
    for n in ("buscar_sentencias", "leer_sentencia", "cendoj_analizar_cita"):
        s.add_tool(lambda: "x", name=n)
    return s


def test_cendoj_fuera_aunque_se_pidan_todas():
    assert remoto.aplicar_perfil(_servidor_con_cendoj(), "todas") == ["dos", "uno"]
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.aplicar_perfil(_servidor_con_cendoj(), "uno,leer_sentencia")


def test_cendoj_solo_con_valor_explicito():
    quedan = remoto.aplicar_perfil(_servidor_con_cendoj(), "todas", cendoj_propio=True)
    assert "buscar_sentencias" in quedan
    base = {"IURIS_HTTP_TOKEN": TOKEN}
    assert not remoto.config_desde_entorno(env=base).cendoj_propio
    assert remoto.config_desde_entorno(
        env={**base, "IURIS_CENDOJ_REMOTO": "uso-profesional-propio"}).cendoj_propio
    with pytest.raises(remoto.ErrorConfiguracion):
        remoto.config_desde_entorno(env={**base, "IURIS_CENDOJ_REMOTO": "1"})


def test_todas_del_servidor_real_sin_cendoj():
    import server

    nombres = [t.name for t in server.mcp._tool_manager.list_tools()]
    quedan = remoto.nombres_perfil("todas", nombres)
    assert not [n for n in quedan if remoto.es_cendoj(n)]
    assert {"buscar_sentencias", "leer_sentencia", "descargar_sentencia"} <= set(nombres)


def test_cendoj_bloqueado_dentro_de_otras_tools(monkeypatch):
    import asyncio

    from sources import cendoj_live, verificacion

    monkeypatch.setenv("IURIS_SIN_CENDOJ", "1")
    assert asyncio.run(cendoj_live.leer_sentencia(roj="STS 1177/2014")) == remoto.AVISO_CENDOJ
    assert asyncio.run(cendoj_live.buscar_sentencias(consulta="x")) == remoto.AVISO_CENDOJ
    assert asyncio.run(verificacion.buscar_por_cita("STS 1177/2014")).find("CENDOJ no esta") >= 0
