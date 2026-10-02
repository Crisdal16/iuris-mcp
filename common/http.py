"""Cliente HTTP comun: honesto, con timeouts y reintentos.

Uso EXCLUSIVO para fuentes con API oficial abierta (BOE, Catastro...). NUNCA
para el CENDOJ: alli el acceso lo hace el usuario en su navegador (ver
sources/cendoj.py). El User-Agent se identifica de verdad, se respeta un
timeout y se reintenta solo ante fallos transitorios.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

USER_AGENT = "iuris-mcp/0.1 (servidor MCP juridico de uso profesional propio)"

DEFAULT_TIMEOUT = 30.0

_TRANSIENT = (httpx.TransportError, httpx.ReadTimeout, httpx.ConnectTimeout)


@retry(
    retry=retry_if_exception_type(_TRANSIENT),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=6),
    reraise=True,
)
def get(url: str, *, accept: str = "application/json", params: dict | None = None,
        timeout: float = DEFAULT_TIMEOUT) -> httpx.Response:
    """GET con reintentos ante fallos de red. Lanza para 4xx/5xx via raise_for_status."""
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    resp = httpx.get(url, headers=headers, params=params, timeout=timeout,
                     follow_redirects=True)
    resp.raise_for_status()
    return resp


def get_json(url: str, *, params: dict | None = None,
             timeout: float = DEFAULT_TIMEOUT) -> dict:
    return get(url, accept="application/json", params=params, timeout=timeout).json()


def get_xml(url: str, *, params: dict | None = None,
            timeout: float = DEFAULT_TIMEOUT) -> str:
    return get(url, accept="application/xml", params=params, timeout=timeout).text


def describir_error(e: Exception) -> str:
    """Error de red legible: distingue 'el servidor oficial esta caido' (5xx)
    de un fallo nuestro, para que Claude no reintente en bucle."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code >= 500:
            return f"el servidor oficial no responde (HTTP {code}); es una incidencia suya, prueba mas tarde"
        return f"HTTP {code}"
    if isinstance(e, (httpx.TimeoutException,)):
        return "tiempo de espera agotado; el servidor oficial va lento o esta caido"
    if isinstance(e, httpx.TransportError):
        return f"sin conexion con el servidor oficial ({type(e).__name__})"
    return f"{type(e).__name__}: {e}"
