#!/usr/bin/env python3
"""Comprueba que los proxies de proxies.txt funcionan de verdad.

Uso:
    python check_proxies.py                    # lee proxies.txt de la raiz
    python check_proxies.py /otra/ruta.txt     # o el fichero que digas
    python check_proxies.py --url https://httpbin.org/ip

Para cada proxy hace una peticion real y muestra la IP de salida (o el error),
usando el MISMO parser de formatos que usa la rotacion (ip:puerto,
ip:puerto:usuario:clave, http://usuario:clave@ip:puerto).

Ideal para validar las 10 proxies gratuitas de Webshare antes de activar
IURIS_ROTACION=true. Codigo de salida: 0 si al menos una esta viva.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

import httpx

from common.ip_rotator import parse_proxy

RAIZ = os.path.dirname(os.path.abspath(__file__))
POR_DEFECTO = os.path.join(RAIZ, "proxies.txt")
URL_TEST = "http://httpbin.org/ip"


def _url_cliente(p) -> str:
    """URL httpx del proxy, con credenciales si las hay."""
    cred = f"{p.username}:{p.password}@" if p.username else ""
    return f"{p.scheme}://{cred}{p.host}:{p.port}"


def comprobar(linea: str, url_test: str, timeout: float) -> tuple[str, bool, str]:
    """Devuelve (linea, viva, detalle)."""
    try:
        p = parse_proxy(linea)
    except ValueError as e:
        return linea, False, f"formato invalido: {e}"
    t0 = time.monotonic()
    try:
        r = httpx.get(
            url_test, proxy=_url_cliente(p), timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0"},
        )
        ms = (time.monotonic() - t0) * 1000
        if r.status_code != 200:
            return linea, False, f"HTTP {r.status_code}"
        salida = json.loads(r.text).get("origin", "?")
        return linea, True, f"salida {salida}  ({ms:.0f} ms)"
    except Exception as e:
        return linea, False, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida los proxies de un fichero.")
    ap.add_argument("fichero", nargs="?", default=POR_DEFECTO)
    ap.add_argument("--url", default=URL_TEST)
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    if not os.path.exists(args.fichero):
        print(f"No existe {args.fichero}. Copia proxies.ejemplo.txt -> proxies.txt "
              "y pon tus IPs (una por linea).")
        return 2

    with open(args.fichero, encoding="utf-8") as f:
        lineas = [l.strip() for l in f
                  if l.strip() and not l.strip().startswith("#")]
    if not lineas:
        print(f"{args.fichero} no tiene proxies (solo comentarios o vacio).")
        return 2

    print(f"Comprobando {len(lineas)} proxies contra {args.url} …\n")
    vivas = 0
    with cf.ThreadPoolExecutor(min(10, len(lineas))) as ex:
        for linea, ok, detalle in ex.map(
            lambda l: comprobar(l, args.url, args.timeout), lineas
        ):
            print(f"  {'VIVA ' if ok else 'CAIDA'}  {linea:40}  {detalle}")
            vivas += ok

    print(f"\nResultado: {vivas}/{len(lineas)} vivas.")
    if vivas:
        print("Listo: activa la rotacion con IURIS_ROTACION=true "
              "(el pool ignora solo las que fallen al usarlas).")
        return 0
    print("Ninguna viva: revisa credenciales o consigue otras IPs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
