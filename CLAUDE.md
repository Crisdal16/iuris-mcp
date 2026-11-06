# iuris-mcp — notas para Claude

Servidor MCP propio (Python, stdio) de fuentes jurídicas oficiales. Ver README.md
(qué hace) y FICHA-iuris-mcp.md (registro e historia).

## Entorno (Windows)

- Python: `C:\dev\iuris-mcp\.venv\Scripts\python.exe` (instalacion buena con rotacion
  de IPs; el MCP de Claude apunta aqui). El venv antiguo `C:\Users\crist\iuris-mcp-venv`
  y la copia de OneDrive estan obsoletos. El `.venv/` de esta carpeta en otros equipos
  (Mac) no se usa: cada maquina crea el suyo.
- NO usar `python3`: en esta máquina es el alias de la Microsoft Store y se cuelga.
- Rotacion de IPs: activada solo con `IURIS_ROTACION=true` (ya fijada con setx) y
  `proxies.txt` en la raiz. En la nube NO se usan proxies para CENDOJ (reglas abajo).
- Contenedor/nube: si Chromium no arranca por desajuste pip/contenedor, fijar
  `IURIS_CHROMIUM_PATH` al binario real (p. ej. `/opt/pw-browsers/chromium`).
- Para imprimir tildes en consola: `python -X utf8`.
- Parchear ficheros con Edit, no con heredocs de bash: el shell se come las
  barras invertidas (`\\` → `\`) y rompe regex y rutas.
- Tests: `python -m pytest -q -m "not red"` (sin red, <1 s) y `-q` (con red, ~1 min).
- Tras cambiar `server.py`, el MCP hay que reiniciarlo para que Claude vea los cambios.

## Cómo trabaja este repo (para el agente)

- Este es el servidor MCP personal del titular del repo: consulta jurídica
  profesional propia, documento a documento. Es el uso para el que está
  construido todo el diseño (cache, lecturas recortadas, pool de IPs).
- CENDOJ: `buscar_sentencias` (navegador real) + `leer_sentencia` /
  `descargar_sentencia` (descarga directa, con cache). Con la rotación activa
  (`IURIS_ROTACION=true`) las peticiones salen por el pool del titular y una IP
  que falla cede el turno a la siguiente automáticamente: no hace falta hacer
  nada especial, ni reintentar a mano.
- Si una descarga termina en captcha, la tool devuelve el mensaje y el ENLACE
  OFICIAL del PDF: pásaselo al usuario para abrirlo en su navegador. No
  reintentar en bucle (gasta pool y no cambia nada) y no usar servicios de
  terceros para el captcha.
- Ritmo: una o pocas resoluciones por consulta, tal cual se pida. Barridos o
  paginaciones masivas no son el uso previsto (además de lo que dice el aviso
  legal del CENDOJ, inutilizan el pool y acaban en bloqueo del PC o de las IPs).
- Todo es de LECTURA. Solo escriben en disco las tools de guardar/descargar, y
  siempre pasando por `common.texto.ruta_permitida` / `dir_destino`.
- Textos largos: recortar con `common.lecturas.recortar` / `common.texto.truncar`,
  que dejan el resto disponible para `continuar_lectura`.
- Las tools se registran con `@herramienta(...)` en server.py (anotaciones +
  `structured_output=False`). Las nuevas van también en `INSTRUCCIONES` si cambian
  qué tool usar para qué.
- Errores de red: `common.http.describir_error` (distingue servidor oficial caído).

## Trampas conocidas de las fuentes

- CENDOJ `accessToPDF` puede redirigir a `captcha.jsp` («Control · Descargas masivas»)
  cuando la IP lleva varias descargas seguidas o esta señalada (típico en nube/contenedor
  compartido). `ErrorCaptcha` (cendoj_live) lo detecta por URL/HTML y responde con el
  enlace oficial del PDF. Con rotación activa, primero prueba el pool automáticamente.
- En contenedor/nube, si Chromium no arranca por desajuste de build: `IURIS_CHROMIUM_PATH`.
- BOE `/texto/bloque/<id>` trae TODAS las redacciones; la primera es la original.
  Usar `boe.elegir_version` (bug real corregido en v0.2.0; test de regresión en
  tests/test_boe.py).
- La API del BOE admite búsqueda en servidor: `boe.consultar_api` con sintaxis
  `titulo:(a and b)`, `numero_oficial:"29/1998"`, `rango@codigo:1300`,
  `ambito@codigo:1` (estatal). Códigos de rango: LO 1290, Ley 1300, RDLeg 1310,
  RDL 1320, RD 1340.
- CELLAR: documentos recientes en XHTML; los antiguos solo en `text/html`.
- PETETE (DGT) da 502 intermitentes: es suyo, no nuestro.
- Cualquier plazo o requisito que se escriba en `sources/escritos.py` debe
  contrastarse antes con `buscar_articulo` (redacción vigente).
