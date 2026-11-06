"""Rotacion de IPs para el CENDOJ (opcional, apagada por defecto).

Si `IURIS_ROTACION=true`, las dos operaciones que hablan con el CENDOJ — la
descarga directa del PDF (httpx) y el navegador de busqueda (Playwright) —
salen por una IP de un pool de proxies propios y rotan automaticamente cuando
la IP falla (403/429/503, timeout, proxy caido o el control anti-bot del sitio).

- Pool: `IURIS_PROXIES=/ruta/proxies.txt` (por defecto `proxies.txt` en la
  raiz del repo; NO se publica: esta en .gitignore). Una IP por linea:
  ip:puerto | ip:puerto:usuario:clave | http://usuario:clave@ip:puerto
- IPs distintas por operacion: `IURIS_ROTACION_MAX` (5 por defecto; max 99).
- Auto-recovery: la IP que falla entra en cooldown (5 min) y vuelve sola a la
  rotacion; si acumula fallos consecutivos se marca «muerta» y se re-testea a
  los 30 min. Sin hilos de fondo: todo perezoso, al usar el pool.

Limites honestos: la rotacion NO elude el captcha del CENDOJ ni autoriza la
descarga masiva; solo evita que un baneo o limitacion temporal de la IP deje
a medias la consulta profesional propia, documento a documento.

La libreria vive vendida en `common/ip_rotator` (stdlib + httpx, ya presente
en el proyecto: sin dependencias nuevas).
"""

from __future__ import annotations

import os
import threading
import time

import httpx

from common.ip_rotator import MAX_POOL_SIZE, ProxyRotator

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_rotador: ProxyRotator | None = None
_intentado = False
_lock = threading.Lock()

# Codigos que el CENDOJ (y la mayoria de WAF) usan para 'esta IP no pasa'.
_BLOQUEANTES = (403, 429, 503)


def _fichero_proxies() -> str:
    return os.environ.get("IURIS_PROXIES") or os.path.join(_RAIZ, "proxies.txt")


def _cargar() -> ProxyRotator | None:
    """Carga el pool una sola vez por proceso.

    Devuelve None si la rotacion esta apagada, el fichero no existe o no hay
    proxies validos: en ese caso el proyecto sigue funcionando como siempre
    (una sola IP, la propia).
    """
    global _rotador, _intentado
    with _lock:
        if _intentado:
            return _rotador
        _intentado = True
        if os.getenv("IURIS_ROTACION", "").strip().lower() not in (
            "1", "true", "yes", "si", "sí",
        ):
            return None
        ruta = _fichero_proxies()
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                lineas = [l.strip() for l in f
                          if l.strip() and not l.strip().startswith("#")]
        except OSError:
            return None
        if not lineas:
            return None
        rot = ProxyRotator(
            strategy="round_robin",
            cooldown_seconds=300.0,
            dead_revive_seconds=1800.0,
            max_consecutive_failures=3,
            request_timeout=30.0,
            max_rotations=MAX_POOL_SIZE,
            retry_status=_BLOQUEANTES,
            polite_delay=1.5,
            max_pool_size=MAX_POOL_SIZE,
        )
        rot.add_many(lineas)
        _rotador = rot if len(rot) else None
        return _rotador


def activa() -> bool:
    """True si la rotacion esta activada y hay pool cargado."""
    return _cargar() is not None


def max_intentos() -> int:
    """IPs distintas a probar por operacion (1 si esta apagada: sin cambios)."""
    rot = _cargar()
    if rot is None:
        return 1
    try:
        n = int(os.getenv("IURIS_ROTACION_MAX", "5"))
    except ValueError:
        n = 5
    return max(1, min(n, MAX_POOL_SIZE))


def reiniciar_para_tests() -> None:
    """Obliga a recargar configuracion (uso en tests)."""
    global _rotador, _intentado
    with _lock:
        _rotador = None
        _intentado = False


def reportar(proxy_id: str, ok: bool, detalle: str = "") -> None:
    """Alimenta el auto-recovery con el resultado de una operacion."""
    rot = _cargar()
    if rot is None or not proxy_id:
        return
    if ok:
        rot.report_success(proxy_id)
    else:
        rot.report_failure(proxy_id, detalle or "fallo")


def proxy_para_navegador() -> dict | None:
    """Proxy para chromium.launch() con claves Playwright, o None.

    {'id': 'host:puerto', 'server': 'http://host:puerto',
     'username': ..., 'password': ...} (username/password solo si hay auth).
    """
    rot = _cargar()
    if rot is None:
        return None
    px = rot.next_proxy()
    if not px:
        return None
    out: dict = {"id": px["id"], "server": f"http://{px['host']}:{px['port']}"}
    if px.get("username"):
        out["username"] = px["username"]
        out["password"] = px.get("password") or ""
    return out


async def descargar_con_rotacion(
    url: str,
    *,
    headers: dict | None = None,
    cookies: dict | None = None,
    timeout: float = 30.0,
    max_ips: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes | None:
    """GET con rotacion de IP. Devuelve los bytes SOLO si la respuesta es 200
    y su cuerpo empieza por %PDF; None si se agotan las IPs o el recurso no
    es un PDF (mismo contrato que _descargar_pdf_httpx).

    Semantica por intento:
      - 200 + PDF    -> exito, se devuelve.
      - 403/429/503  -> la IP queda en cooldown y se prueba la siguiente.
      - otro codigo  -> la IP funciona, el recurso no; no se penaliza.
      - excepcion    -> proxy caido/timeout; siguiente IP.
    `transport` existe para los tests (httpx.MockTransport, sin red).
    """
    rot = _cargar()
    if rot is None:
        return None
    quedan = max(1, min(max_ips or max_intentos(), MAX_POOL_SIZE))
    probadas: set[str] = set()
    for _ in range(quedan):
        px = rot.next_proxy(exclude=probadas)
        if not px:
            break  # pool agotado (todas en cooldown/dead)
        probadas.add(px["id"])
        t0 = time.monotonic()
        try:
            # httpx da prioridad a `proxy` sobre `transport`: son excluyentes.
            # Con transport (tests, MockTransport) no se pasa proxy.
            kwargs: dict = {
                "headers": headers, "cookies": cookies or {},
                "follow_redirects": True, "timeout": timeout,
            }
            if transport is not None:
                kwargs["transport"] = transport
            else:
                kwargs["proxy"] = px["url"]
            async with httpx.AsyncClient(**kwargs) as cli:
                r = await cli.get(url)
            if r.status_code == 200:
                if r.content[:4] == b"%PDF":
                    rot.report_success(px["id"], time.monotonic() - t0)
                    return r.content
                rot.report_success(px["id"], time.monotonic() - t0)
                return None  # IP valida, recurso no-PDF
            if r.status_code in _BLOQUEANTES:
                rot.report_failure(px["id"], f"HTTP {r.status_code}")
                continue
            # Otro codigo (404, 500...): hubo respuesta HTTP, la IP funciona;
            # no se penaliza y no se devuelve contenido parcial.
            rot.report_success(px["id"], time.monotonic() - t0)
            return None
        except Exception as e:
            rot.report_failure(px["id"], f"{type(e).__name__}: {e}"[:200])
            continue
    return None


def linea_estado() -> str | None:
    """Linea de diagnostico para la tool `estado`. None si esta apagada."""
    rot = _cargar()
    if rot is None:
        return None
    s = rot.stats()
    b = s["by_status"]
    return ("Rotacion de IPs: activa — %d/%d proxies en pool (%d activas, "
            "%d en cooldown, %d muertas, %d sin probar); peticiones: %d "
            "(exito %.0f%%); max %d IPs por operacion." % (
                s["pool_size"], s["max_pool_size"], b["active"], b["cooldown"],
                b["dead"], b["untested"], s["total_requests"],
                s["success_rate"] * 100, max_intentos()))
