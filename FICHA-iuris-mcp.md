# Ficha de referencia — iuris-mcp (proyecto propio)

**Qué es:** servidor MCP **local** propio (Python, stdio) que da acceso a fuentes
jurídicas oficiales españolas y de la UE desde Claude Code. Corre en tu Mac; no es
un conector de terceros en la nube.

**Ubicación del código:** `PROYECTOS DEFINTIVIO/iuris-mcp/`
(`server.py`, `sources/`, `common/`, `tests/`, `pyproject.toml`, `README.md`).

**Confirmado como tuyo el:** 2026-08-30. La herramienta `estado` del MCP activo
en Claude Code coincide con este código fuente (mismo listado de fuentes/tools).

## Registro en Claude Code (scope user)

### macOS
```bash
claude mcp add iuris --scope user -- "$HOME/iuris-mcp/.venv/bin/python" "$HOME/iuris-mcp/server.py"
```

> Nota: el registro usa `$HOME/iuris-mcp/...`. El código "de verdad" vive en
> OneDrive (`PROYECTOS DEFINTIVIO/iuris-mcp`). Revisar si `~/iuris-mcp` es esta
> carpeta, un symlink o una copia, para no editar dos sitios distintos.

### Windows (instalado 2026-08-30)
El `.venv/` que hay en la carpeta es de **Mac** (`bin/`, no sirve en Windows y NO
se toca). En Windows se crea un venv propio **fuera de OneDrive** (para no ensuciar
la sincronización) y se apunta al código de OneDrive:

```powershell
python -m venv "C:\Users\crist\iuris-mcp-venv"
& "C:\Users\crist\iuris-mcp-venv\Scripts\python.exe" -m pip install -e "C:\Users\crist\OneDrive\PROYECTOS DEFINTIVIO\iuris-mcp"
claude mcp add iuris --scope user -- "C:\Users\crist\iuris-mcp-venv\Scripts\python.exe" "C:\Users\crist\OneDrive\PROYECTOS DEFINTIVIO\iuris-mcp\server.py"
claude mcp list   # debe decir: iuris ... ✓ Connected
```

Verificado en esta máquina: Python 3.14.3, `mcp 2.1.1`, `pymupdf 1.28.2`,
`selectolax 0.4.11` (todas con wheel cp314). `server.py` importa y `estado()`
responde. Registrado en `C:\Users\crist\.claude.json` (scope user), health-check
✓ Connected. Se ve como `mcp__iuris__*` a partir de la siguiente sesión.

**CENDOJ en vivo (añadido 2026-09-16/17):** requiere Playwright + Chromium en el
venv de Windows (ya instalados: `playwright 1.63.0`, Chromium 153 en
`%LOCALAPPDATA%\ms-playwright`). Si se recrea el venv:

```powershell
& "C:\Users\crist\iuris-mcp-venv\Scripts\python.exe" -m playwright install chromium
```

Tras cualquier cambio en `server.py` hay que **reiniciar el MCP** (o la app) para
que Claude vea las tools nuevas.

## Modo remoto (HTTP) — añadido 2026-10-23

Para que monitorio-ia (auditor de demandas, vía conector MCP de la API de Claude,
beta `mcp-client-2025-11-20`) verifique en el BOE los artículos citados. **stdio sigue
siendo el modo por defecto** y el registro de Claude Code no cambia. Detalle completo
(variables, systemd, Caddy/Nginx, snippet del conector) en README → «Modo remoto (HTTP)».

- Arranque: `IURIS_HTTP_TOKEN=<32+ caracteres> python server.py --http`
  (o `IURIS_TRANSPORT=http`). Escucha en `127.0.0.1:8790/mcp`; el 8765 lo usa otra
  app local. Sin token no arranca; sin cabecera Bearer válida → 401; >60 pet/min por
  token → 429. `GET /salud` sin token para el proxy.
- Código: `common/remoto.py` (middleware Bearer con `hmac.compare_digest`, límite por
  minuto, perfil de tools, `TransportSecuritySettings` con `IURIS_ALLOWED_HOSTS`).
  Usa `MCPServer.streamable_http_app(stateless_http=True, json_response=True)` de
  `mcp 2.1.1`.
- Perfil `IURIS_TOOLS=auditor` por defecto: buscar_articulo, buscar_boe, leer_boe,
  buscar_por_cita, verificar_escrito, computo_plazo, calendario_laboral,
  continuar_lectura. `todas` = todas menos CENDOJ.
- En remoto las tools no leen ni escriben ficheros del servidor (`IURIS_SIN_DISCO=1`).
- **CENDOJ SIEMPRE fuera en remoto.** Aviso legal del CENDOJ: «No está permitida la
  utilización de la base de datos para usos comerciales, ni la descarga masiva»; la
  reutilización comercial va por el procedimiento del CGPJ (LRISP). El modo remoto lo
  usará un producto de pago, así que `buscar_sentencias`, `leer_sentencia`,
  `descargar_sentencia` y `cendoj_*` quedan fuera aunque se pida `todas`, y
  `buscar_por_cita` / `verificar_escrito` no consultan el CENDOJ (`IURIS_SIN_CENDOJ=1`).
  Solo se reactivan con `IURIS_CENDOJ_REMOTO=uso-profesional-propio` o
  `--cendoj-uso-profesional-propio`: **solo uso profesional propio, nunca para
  monitorio-ia ni otro servicio comercial.**
- Tests: `tests/test_remoto.py` (sin red). Prueba real hecha en local el 2026-10-23
  (cliente streamable-http de la librería: 401 sin token, lista de 8 tools,
  `buscar_articulo(LEC, 813)` correcto). **No desplegado en ningún VPS.**

## Instalación / tests

```bash
cd iuris-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest -q
```

## Stack

Python ≥3.11 · `mcp>=1.2.0`, `httpx`, `pymupdf`, `selectolax`, `tenacity`, `diskcache`,
`playwright` (+ `playwright install chromium`).

## Herramientas — tres regímenes (lista histórica; la vigente en README)

**Jurisprudencia en vivo (bajo demanda):**

*TC (`sources/tc.py`, HTTP plano, sin navegador):*
- `buscar_tc` — texto libre (con `ambito`: todo/fundamentos/fallo/…), cita
  (`STC 31/2010`), número+año, ECLI, tipo, materia, fechas, `pagina`. Devuelve
  síntesis descriptiva y analítica + `id`.
- `leer_tc` — por id / cita / ECLI; `seccion` (fallo, fundamentos, antecedentes,
  votos, ficha, extractos), `palabras_clave`, `guardar_md`. Flujo: GET Index →
  token anti-forgery → POST Buscar → List (`?page=N`) → Show/<id> (HTML seccionado
  por `#antecedentes-container`, `#fundamentos-container`, `#dictamen-container`…).

*TJUE / Tribunal General (`sources/tjue.py`, CELLAR = API oficial de la UE):*
- `buscar_tjue` — palabras del título (SPARQL, ~10-20 s), asunto (`C-311/18`:
  lista sentencia/conclusiones/autos) o ECLI. `desde/hasta`, `tribunal`.
- `leer_tjue` — por asunto / ECLI / CELEX; `tipo` (sentencia, conclusiones, auto);
  `seccion='fallo'`; `palabras_clave`; `guardar_md`. CELEX = `6 + año + CJ|TJ|CC|CO + nº`;
  documento en español vía `publications.europa.eu/resource/celex/<CELEX>` con
  `Accept: application/xhtml+xml` + `Accept-Language: es`. EUR-Lex/CURIA bloquean bots;
  CELLAR no.

*CENDOJ (`sources/cendoj_live.py`, navegador real para buscar):*
- `buscar_sentencias` — texto libre + filtros (jurisdicción, CCAA/provincia, fechas,
  ROJ, ECLI, ponente, norma, nº recurso/resolución), `maximo` hasta 50, `pagina`,
  `orden` (fecha / relevancia / antiguas / nuevo / órgano). Tarda 10-30 s.
- `leer_sentencia` — texto por `url` (directo, ~2 s, sin navegador) o ROJ/ECLI;
  `seccion` ('fallo', 'fundamentos', 'antecedentes', 'hechos', 'encabezado'),
  `palabras_clave` (solo los párrafos que las contienen), `guardar_pdf`/`guardar_md`.
- `descargar_sentencia` — guarda PDF / MD / ambos en `ruta` sin volcar texto.
- Caché en `.cache/cendoj` (bytes + texto por referencia). Límite del sitio: ~6-7
  descargas por sesión; cada descarga va sin sesión previa, así que no se acumula.

**Automático (API/servicio oficial, sin captcha):**
- BOE / legislación: `buscar_articulo` (texto vigente consolidado), `buscar_boe`,
  `novedades_boe`, `sumario_boe`, `leer_boe`
- Catastro (OVC): `consultar_catastro`, `callejero_catastro` (sin titular ni valor;
  no cubre País Vasco ni Navarra)
- Mercantil (BORME): `sumario_borme`
- Fiscal DGT: `buscar_consultas_hacienda`, `leer_consulta_hacienda`
- Fiscal TEAC/TEAR: `buscar_doctrina_teac`, `leer_resolucion_teac`
- Convenios: `leer_convenio`

**Humano en el bucle (el servidor prepara la búsqueda/enlace oficial; el acceso lo
haces tú en tu navegador, sin evasión de anti-bot):**
- CENDOJ (respaldo offline): `cendoj_construir_busqueda`, `cendoj_analizar_cita`
- Convenios REGCON: `buscar_convenio`, `vigencia_convenio`
- Empresa (RM): `buscar_empresa_mercantil`
- UE (EUR-Lex, normativa): `buscar_norma_ue`
- Diagnóstico: `estado`

**Añadido en v0.2.0 (2026-10-02):** `continuar_lectura`, `buscar_por_cita`,
`verificar_escrito`, `guia_escrito`, `buscar_ordenanzas` (35 tools en total; la
lista al día la da `estado()` y el README). Corregido: `buscar_articulo` devolvía
la redacción ORIGINAL de cada artículo en vez de la vigente.

## Notas de diseño

- **CENDOJ en vivo**: la búsqueda conduce un Chromium real (Playwright): teclea la
  consulta carácter a carácter y elige una sugerencia del autocompletado, que es
  como el sitio espera que se use (evita el "Control de grandes paginaciones").
  Los desplegables del listado son bootstrap-select con el `<select>` oculto y la
  paginación es `display:none`: se manejan por JS (`goToPage('jurisprudencia', n)`,
  `dispatchEvent('change')`) y se espera a que el listado cambie de verdad.
  La lectura NO necesita navegador: la URL de ficha `openDocument/<ref>/<opt>`
  se traduce al enlace directo `contenidos.action?action=accessToPDF&reference=
  <ref>&optimize=<opt>…` (patrón tomado de la extensión `cendoj-extractor`).
  Uso profesional propio, documento a documento; no masivo ni BD derivada.
- **CENDOJ respaldo**: `cendoj_construir_busqueda`/`cendoj_analizar_cita` no tocan
  la red; construyen la URL/filtros oficiales para que accedas tú.
- **TLS DGT/PETETE**: la cadena TLS de la DGT omite el intermedio de la FNMT; se
  **completa** con el intermedio oficial (`common/certs/`) en vez de desactivar la
  verificación. Ver `sources/dgt.py`.

## Ojo: hay un segundo MCP jurídico solapado

En Claude Code también está conectado **"Jurisprudenciator"**
(`mcp__b8518599-...`), con herramientas casi idénticas (BOE, sentencias, TC, TJUE,
hacienda...). Es el MCP de **DerechoVirtual/mcp-cendoj-sentencias** (código no
público; identificado el 2026-09-17 por su ficha en glama.ai). Desde el 2026-09-17
iuris cubre lo mismo en CENDOJ (búsqueda + lectura + párrafos por tema) y añade
secciones, descarga a expediente y caché local. Desde el 2026-09-17 iuris también
trae **TC y TJUE a texto** (`buscar_tc`/`leer_tc`, `buscar_tjue`/`leer_tjue`).

**Revisión 2026-10-02 (v0.2.0):** la afirmación anterior de que "ya no hay nada que
Jurisprudenciator haga y iuris no" no era exacta. Le faltaban a iuris
`continuar_lectura`, `buscar_por_cita`, `verificar_escrito`, `guia_escrito` y
`buscar_ordenanzas`, y desde la v0.2.0 los tiene todos. Diferencias que quedan:
- Jurisprudenciator busca ordenanzas automáticamente en 13 catálogos municipales y
  41 BOP; iuris da el BOP verificado y lee el anuncio con `leer_boletin` (humano en
  el bucle).
- Jurisprudenciator tiene más guías de escritos (habeas corpus, orden de protección,
  burofax, hoja de encargo...); iuris tiene 11, con la base legal comprobada en vivo
  en el BOE.
- El plan gratuito de Jurisprudenciator tiene cupo semanal (agotado el 2026-10-02);
  iuris no tiene límites propios.

## Repos de referencia revisados (2026-09-17)

- `ComputingVictor/MCP-CENDOJ` — base del flujo Playwright (autocompletado,
  selectores del formulario, `expect_download`, caché SQLite). Aprovechado.
- `FrancoMartino/cendoj-extractor` (extensión Chrome) — patrón de la URL directa
  del PDF y del widget "resultados por página". Aprovechado.
- `Gasparms9/Project5-Cendoj-Scrapping-API` — proyecto de estudiante 2022
  (Selenium/requests + MySQL). Solo confirma `object#objtcontentpdf`. Nada más.
- `DerechoVirtual/mcp-cendoj-sentencias` — es Jurisprudenciator; ideas tomadas:
  modo párrafos y aviso del límite de 6-7 descargas por sesión.
