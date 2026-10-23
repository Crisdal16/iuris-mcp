"""Modo remoto (HTTP) de iuris: transporte streamable-http con token Bearer.

stdio sigue siendo el modo por defecto (Claude Code). El modo HTTP existe para que
otro servicio propio (p. ej. el auditor de demandas de monitorio-ia, a traves del
conector MCP de la API de Claude) consulte iuris en un servidor:

  * Autenticacion obligatoria: token Bearer de IURIS_HTTP_TOKEN (uno o varios,
    separados por comas). Sin token configurado el modo HTTP NO arranca.
    Comparacion en tiempo constante (hmac.compare_digest).
  * Escucha por defecto solo en 127.0.0.1: para exponerlo, detras de un proxy
    inverso con HTTPS (Caddy/Nginx). Los Host publicos se declaran en
    IURIS_ALLOWED_HOSTS (proteccion anti DNS-rebinding de la libreria mcp).
  * Perfil de herramientas: IURIS_TOOLS=auditor (por defecto en HTTP: solo
    lectura, sin navegador ni disco), =todas, o una lista separada por comas.
  * CENDOJ SIEMPRE fuera en remoto (aviso legal: no uso comercial ni descarga
    masiva), aunque se pida 'todas'; tampoco lo consultan buscar_por_cita ni
    verificar_escrito. Solo se reactiva con IURIS_CENDOJ_REMOTO=uso-profesional-propio
    (o --cendoj-uso-profesional-propio), nunca para un producto de pago.
  * Limite de peticiones por minuto y token (IURIS_HTTP_RPM, 60 por defecto).
  * Sin acceso al disco del servidor: en HTTP las tools no leen ni guardan
    ficheros (IURIS_SIN_DISCO=1, ver common.texto.ruta_permitida).
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

# Subconjunto de solo lectura util para auditar un escrito (sin navegador CENDOJ,
# sin escritura en disco). continuar_lectura hace falta para los textos recortados.
PERFIL_AUDITOR: tuple[str, ...] = (
    "buscar_articulo",
    "buscar_boe",
    "leer_boe",
    "buscar_por_cita",
    "verificar_escrito",
    "computo_plazo",
    "calendario_laboral",
    "continuar_lectura",
)

PERFILES = {"auditor": PERFIL_AUDITOR}

# CENDOJ en remoto: su aviso legal prohibe "usos comerciales" y "la descarga
# masiva"; la reutilizacion comercial va por el procedimiento del CGPJ (LRISP).
# El modo HTTP lo usara un producto de pago, asi que las tools de CENDOJ quedan
# SIEMPRE fuera (aunque se pida 'todas') y buscar_por_cita / verificar_escrito no
# lo consultan. Solo se reactivan con un valor explicito, para uso profesional propio.
HERRAMIENTAS_CENDOJ: tuple[str, ...] = (
    "buscar_sentencias", "leer_sentencia", "descargar_sentencia",
    "cendoj_construir_busqueda", "cendoj_analizar_cita",
)
VALOR_CENDOJ_PROPIO = "uso-profesional-propio"
AVISO_CENDOJ = (
    "CENDOJ no esta disponible en el modo remoto de iuris: su aviso legal no permite el uso "
    "comercial ni la descarga masiva (la reutilizacion comercial va por el procedimiento del "
    "CGPJ). Consulta la resolucion tu mismo en https://www.poderjudicial.es/search/")


def es_cendoj(nombre: str) -> bool:
    return nombre in HERRAMIENTAS_CENDOJ or nombre.startswith("cendoj_")


def cendoj_bloqueado() -> bool:
    """True en modo remoto salvo que se haya activado el uso profesional propio."""
    return os.environ.get("IURIS_SIN_CENDOJ") == "1"

RPM_POR_DEFECTO = 60
PUERTO_POR_DEFECTO = 8790
RUTA_POR_DEFECTO = "/mcp"
RUTA_SALUD = "/salud"


class ErrorConfiguracion(RuntimeError):
    """La configuracion del modo HTTP no permite arrancar con seguridad."""


# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

@dataclass
class ConfigHTTP:
    tokens: list[str]
    host: str = "127.0.0.1"
    port: int = PUERTO_POR_DEFECTO
    path: str = RUTA_POR_DEFECTO
    tools: str = "auditor"
    rpm: int = RPM_POR_DEFECTO
    allowed_hosts: list[str] = field(default_factory=list)
    cendoj_propio: bool = False  # SOLO uso profesional propio (nunca el producto de pago)


def leer_tokens(valor: str | None) -> list[str]:
    """Tokens de IURIS_HTTP_TOKEN. Exige al menos uno y de 32 caracteres o mas."""
    tokens = [t.strip() for t in (valor or "").split(",") if t.strip()]
    if not tokens:
        raise ErrorConfiguracion(
            "Modo HTTP sin token: define IURIS_HTTP_TOKEN (p. ej. "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\"). "
            "iuris no se expone por HTTP sin autenticacion.")
    cortos = [t for t in tokens if len(t) < 32]
    if cortos:
        raise ErrorConfiguracion(
            "IURIS_HTTP_TOKEN demasiado corto: usa tokens aleatorios de 32 caracteres o mas.")
    return tokens


def config_desde_entorno(env: dict[str, str] | None = None, **sobrescribir) -> ConfigHTTP:
    """Construye la configuracion desde variables de entorno; los argumentos de la
    linea de ordenes (no None) tienen prioridad."""
    env = os.environ if env is None else env
    s = {k: v for k, v in sobrescribir.items() if v is not None}
    try:
        rpm = int(s.get("rpm", env.get("IURIS_HTTP_RPM", RPM_POR_DEFECTO)))
        port = int(s.get("port", env.get("IURIS_HTTP_PORT", PUERTO_POR_DEFECTO)))
    except ValueError as e:
        raise ErrorConfiguracion(f"Valor numerico no valido: {e}") from None
    path = s.get("path", env.get("IURIS_HTTP_PATH", RUTA_POR_DEFECTO)) or RUTA_POR_DEFECTO
    if not path.startswith("/"):
        path = "/" + path
    hosts = s.get("allowed_hosts", env.get("IURIS_ALLOWED_HOSTS", ""))
    if isinstance(hosts, str):
        hosts = [h.strip() for h in hosts.split(",") if h.strip()]
    valor_cendoj = env.get("IURIS_CENDOJ_REMOTO", "").strip().lower()
    if valor_cendoj and valor_cendoj != VALOR_CENDOJ_PROPIO:
        raise ErrorConfiguracion(
            f"IURIS_CENDOJ_REMOTO solo admite el valor '{VALOR_CENDOJ_PROPIO}' "
            "(uso profesional propio; nunca para un producto comercial).")
    cendoj_propio = bool(s.get("cendoj_propio")) or valor_cendoj == VALOR_CENDOJ_PROPIO
    return ConfigHTTP(
        cendoj_propio=cendoj_propio,
        tokens=leer_tokens(s.get("token", env.get("IURIS_HTTP_TOKEN"))),
        host=s.get("host", env.get("IURIS_HTTP_HOST", "127.0.0.1")),
        port=port,
        path=path,
        tools=s.get("tools", env.get("IURIS_TOOLS", "auditor")),
        rpm=max(0, rpm),
        allowed_hosts=list(hosts),
    )


# --------------------------------------------------------------------------
# Perfil de herramientas
# --------------------------------------------------------------------------

def nombres_perfil(perfil: str, disponibles: list[str], cendoj_propio: bool = False) -> list[str]:
    """'todas', un perfil con nombre ('auditor') o una lista separada por comas.
    Las tools de CENDOJ quedan fuera salvo cendoj_propio=True (uso profesional propio)."""
    p = (perfil or "auditor").strip()
    if p.lower() in ("todas", "all", "*"):
        return sorted(n for n in disponibles if cendoj_propio or not es_cendoj(n))
    nombres = list(PERFILES.get(p.lower(), [n.strip() for n in p.split(",") if n.strip()]))
    desconocidas = [n for n in nombres if n not in disponibles]
    if desconocidas:
        raise ErrorConfiguracion(f"IURIS_TOOLS: herramientas desconocidas: {', '.join(desconocidas)}")
    vedadas = [n for n in nombres if es_cendoj(n) and not cendoj_propio]
    if vedadas:
        raise ErrorConfiguracion(
            f"IURIS_TOOLS pide herramientas de CENDOJ ({', '.join(vedadas)}), vedadas en remoto. "
            f"Solo para uso profesional propio: IURIS_CENDOJ_REMOTO={VALOR_CENDOJ_PROPIO}.")
    if not nombres:
        raise ErrorConfiguracion("IURIS_TOOLS no selecciona ninguna herramienta")
    return nombres


def aplicar_perfil(mcp, perfil: str, cendoj_propio: bool = False) -> list[str]:
    """Quita del servidor las tools fuera del perfil. Devuelve las que quedan."""
    disponibles = [t.name for t in mcp._tool_manager.list_tools()]
    quedan = set(nombres_perfil(perfil, disponibles, cendoj_propio))
    for n in disponibles:
        if n not in quedan:
            mcp.remove_tool(n)
    return sorted(quedan)


# --------------------------------------------------------------------------
# Middleware ASGI: token Bearer + limite por minuto
# --------------------------------------------------------------------------

class LimitePorMinuto:
    """Ventana deslizante de 60 s por clave (indice del token)."""

    def __init__(self, rpm: int, reloj=time.monotonic):
        self.rpm = rpm
        self._reloj = reloj
        self._golpes: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def permitir(self, clave: int) -> tuple[bool, int]:
        """(permitido, segundos hasta poder reintentar)."""
        if self.rpm <= 0:
            return True, 0
        ahora = self._reloj()
        with self._lock:
            q = self._golpes.setdefault(clave, deque())
            while q and ahora - q[0] >= 60:
                q.popleft()
            if len(q) >= self.rpm:
                return False, max(1, int(60 - (ahora - q[0])) + 1)
            q.append(ahora)
            return True, 0


async def _responder(send, status: int, cuerpo: str, cabeceras: list[tuple[bytes, bytes]] = ()) -> None:
    datos = cuerpo.encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(datos)).encode()), *cabeceras],
    })
    await send({"type": "http.response.body", "body": datos})


class AutenticacionBearer:
    """Exige `Authorization: Bearer <token>` en todo salvo GET /salud.

    401 sin token o con token incorrecto (WWW-Authenticate: Bearer); 429 si se
    supera el limite por minuto. El ciclo 'lifespan' pasa sin tocar.
    """

    def __init__(self, app, tokens: list[str], rpm: int = RPM_POR_DEFECTO,
                 limite: LimitePorMinuto | None = None):
        if not tokens:
            raise ErrorConfiguracion("AutenticacionBearer sin tokens")
        self.app = app
        self._tokens = [t.encode("utf-8") for t in tokens]
        self.limite = limite or LimitePorMinuto(rpm)

    def _token_valido(self, cabecera: bytes) -> int | None:
        esquema, _, valor = cabecera.partition(b" ")
        if esquema.lower() != b"bearer" or not valor.strip():
            return None
        valor = valor.strip()
        encontrado = None
        for i, t in enumerate(self._tokens):  # se comparan TODOS: tiempo constante
            if hmac.compare_digest(valor, t):
                encontrado = i
        return encontrado

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == RUTA_SALUD and scope.get("method") in ("GET", "HEAD"):
            await _responder(send, 200, "ok")
            return
        cabecera = b""
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                cabecera = v
                break
        indice = self._token_valido(cabecera)
        if indice is None:
            await _responder(send, 401, "Falta un token Bearer valido.",
                             [(b"www-authenticate", b'Bearer realm="iuris"')])
            return
        ok, espera = self.limite.permitir(indice)
        if not ok:
            await _responder(send, 429, "Demasiadas peticiones: espera y reintenta.",
                             [(b"retry-after", str(espera).encode())])
            return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------
# App y arranque
# --------------------------------------------------------------------------

def crear_app(mcp, cfg: ConfigHTTP):
    """App ASGI lista para uvicorn: streamable-http de la libreria mcp envuelto
    en AutenticacionBearer. Modo sin estado y respuestas JSON (mas sencillo
    detras de un proxy y para el conector MCP de la API de Claude)."""
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", *cfg.allowed_hosts]
    origenes = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*",
                *[f"https://{h.split(':')[0]}" for h in cfg.allowed_hosts]]
    seguridad = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                          allowed_hosts=hosts, allowed_origins=origenes)
    app = mcp.streamable_http_app(
        streamable_http_path=cfg.path,
        json_response=True,
        stateless_http=True,
        max_request_body_size=2 * 1024 * 1024,
        transport_security=seguridad,
        host=cfg.host,
    )
    return AutenticacionBearer(app, cfg.tokens, rpm=cfg.rpm)


def servir(mcp, cfg: ConfigHTTP) -> None:
    import sys

    import uvicorn

    # Disco del servidor vedado a las tools en remoto (common.texto._sin_disco).
    os.environ["IURIS_SIN_DISCO"] = "1"
    # CENDOJ vedado tambien dentro de buscar_por_cita / verificar_escrito.
    if cfg.cendoj_propio:
        os.environ.pop("IURIS_SIN_CENDOJ", None)
        print("AVISO: CENDOJ activado en remoto. SOLO uso profesional propio: el aviso legal "
              "del CENDOJ no permite usos comerciales ni descarga masiva.", file=sys.stderr)
    else:
        os.environ["IURIS_SIN_CENDOJ"] = "1"
    quedan = aplicar_perfil(mcp, cfg.tools, cfg.cendoj_propio)
    app = crear_app(mcp, cfg)
    if cfg.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"AVISO: escuchando en {cfg.host}; exponlo solo detras de un proxy con HTTPS.",
              file=sys.stderr)
    print(f"iuris-mcp HTTP en http://{cfg.host}:{cfg.port}{cfg.path} · {len(quedan)} herramientas "
          f"· limite {cfg.rpm or 'sin limite'}/min por token", file=sys.stderr)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1", server_header=False)
