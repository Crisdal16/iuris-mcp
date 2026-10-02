# iuris-mcp

Servidor MCP local (stdio, Python) con acceso a fuentes jurídicas **oficiales**
españolas y de la UE: BOE, CENDOJ, Tribunal Constitucional, TJUE, normativa UE,
DGT, TEAC, Catastro, BORME, convenios, boletines autonómicos y ordenanzas.
Versión 0.2.0 · 35 herramientas · todas de lectura (solo escriben en disco las
que guardan una resolución en la carpeta que indiques).

## Herramientas

**Empieza por aquí**
- `buscar_por_cita` — abre *cualquier* cita en su fuente: `STC 31/2010`,
  `STS 1177/2014`, ECLI, `C-311/18`, `art. 1902 CC`, `artículo 46 de la Ley 29/1998`,
  `art. 17 RGPD`, `BOE-A-…`, `V0282-26` (DGT), `00/06291/2024` (TEAC).
- `verificar_escrito` — extrae todas las citas de un borrador (texto o `.docx` /
  `.pdf` / `.md`) y comprueba cada una: existe, está derogada, qué redacción está
  vigente y quién la dio; devuelve la frase del escrito junto al texto oficial.
- `guia_escrito` — método para redactar demandas (verbal, ordinario), contestación,
  monitorio y oposición, apelación, reposición, despido, contencioso, alzada/
  reposición administrativa y querella, con su base legal **vigente comprobada en el
  BOE en el momento** (LO 1/2025: MASC, umbral de 15.000 €…).
- `continuar_lectura` — siguiente tramo de cualquier texto largo recortado.

**Legislación**
- `buscar_articulo` — texto **vigente** de un artículo o disposición (adicional,
  transitoria, final…), con fecha de vigencia, norma que dio la redacción y aviso de
  redacciones futuras. Acepta siglas (LEC, CC, ET, LGT, LOPDGDD, LGSS, LJCA…),
  `Ley 29/1998`, `LO 3/2018`, `RDLeg 8/2015`, BOE-A… y normas UE (`RGPD`,
  `Directiva 93/13/CEE`) vía CELLAR.
- `buscar_boe` (búsqueda en servidor sobre toda la legislación consolidada),
  `sumario_boe`, `novedades_boe`, `leer_boe`, `buscar_norma_ue`.

**Jurisprudencia**
- CENDOJ: `buscar_sentencias` (navegador real, 10-30 s), `leer_sentencia`
  (descarga directa, por sección o párrafos con `palabras_clave`),
  `descargar_sentencia` (PDF/MD al expediente). Respaldo sin red:
  `cendoj_construir_busqueda`, `cendoj_analizar_cita`.
- Tribunal Constitucional: `buscar_tc`, `leer_tc` (texto seccionado).
- TJUE / Tribunal General: `buscar_tjue`, `leer_tjue` (CELLAR, en español).

**Fiscal**: `buscar_consultas_hacienda`, `leer_consulta_hacienda` (DGT);
`buscar_doctrina_teac`, `leer_resolucion_teac` (TEAC/TEAR).

**Laboral y plazos**: `buscar_convenio`, `leer_convenio`, `vigencia_convenio`,
`leer_boletin`, `calendario_laboral`, `computo_plazo`.

**Otros**: `consultar_catastro`, `callejero_catastro`, `sumario_borme`,
`buscar_empresa_mercantil`, `buscar_ordenanzas`, `estado`.

## Tres regímenes de acceso

1. **API o servicio oficial abierto** (BOE, Catastro, BORME, DGT, TEAC, TC, CELLAR):
   automático, sin captcha.
2. **CENDOJ**: su buscador tiene captcha ante clientes no-navegador y su aviso legal
   permite la consulta "para uso particular" pero no la descarga masiva ni construir
   bases derivadas. `buscar_sentencias` conduce un navegador real (Playwright) como lo
   haría una persona; la lectura va por la URL directa del PDF. **Uso profesional
   propio, documento a documento.**
3. **Humano en el bucle** (REGCON, Registro Mercantil, BOP para ordenanzas): el
   servidor prepara la búsqueda oficial y el enlace; el acceso lo haces tú.

## Instalación

```bash
python -m venv <venv>
<venv>/python -m pip install -e ".[dev]"
<venv>/python -m playwright install chromium   # solo para buscar en el CENDOJ
```

En Windows el venv vive fuera de OneDrive (ver `FICHA-iuris-mcp.md`).

Registro en Claude Code:

```bash
claude mcp add iuris --scope user -- "<venv>/python" "<ruta>/server.py"
```

Tras cambiar `server.py`, reinicia el MCP para que Claude vea las tools nuevas.

### Variables de entorno

| Variable | Efecto |
|---|---|
| `IURIS_RAIZ` | Carpeta(s) (separadas por `;` en Windows) dentro de las cuales se permite guardar resoluciones y leer escritos. Sin ella se admite cualquier ruta local (nunca rutas de red UNC). |
| `CENDOJ_HEADLESS=false` | Muestra el navegador del CENDOJ (depuración). |

## Tests y evals

```bash
<venv>/python -m pytest -q -m "not red"   # sin red
<venv>/python -m pytest -q                # incluye las fuentes reales
```

`evals/` contiene 10 preguntas verificadas para medir el servidor con un modelo
(ver `evals/README.md`).

## Notas de diseño

- **Texto vigente**: el BOE devuelve todas las redacciones de un artículo en orden
  cronológico; se elige la vigente hoy (no la primera, que es la original) y se
  avisa si hay una futura. Las notas de reforma del BOE van aparte.
- **Normativa UE**: CELLAR sirve el acto tal como se publicó en el DOUE (versión
  original); la salida lo advierte y enlaza el consolidado de EUR-Lex.
- **Respuestas en texto**: las tools devuelven texto sin `structuredContent`
  (el envoltorio duplicaría cada respuesta en el contexto del modelo).
- **TLS de la DGT**: PETETE presenta una cadena TLS incompleta; se completa con el
  intermedio oficial de la FNMT (`common/certs/`) en lugar de desactivar la
  verificación. Ver `sources/dgt.py`.
- **Errores**: si un servidor oficial está caído (5xx) la respuesta lo dice, para
  que el modelo no reintente en bucle.
