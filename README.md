# iuris-mcp

Servidor MCP local de fuentes jurídicas oficiales españolas. Corre en tu Mac
(stdio) y se conecta a Claude Code.

## CENDOJ: acceso real + respaldo offline

El buscador del CENDOJ (poderjudicial.es) protege el acceso automatizado con un
**captcha** ("Control de grandes paginaciones") que salta ante peticiones de un
cliente no-navegador, y su **aviso legal** permite la consulta "para uso
particular" pero prohíbe el uso comercial, la descarga masiva y construir bases
de datos derivadas.

El servidor ofrece dos vías:

**1. Acceso real (bajo demanda, documento a documento):**

- **`buscar_sentencias`** — busca en el CENDOJ conduciendo un navegador real
  (Playwright): teclea la consulta carácter a carácter y selecciona una
  sugerencia del autocompletado, que es como el propio sitio espera que se use.
  Filtros: jurisdicción, CCAA/provincia, fechas, ROJ, ECLI, ponente, norma, nº
  recurso/resolución; `maximo` hasta 50, `pagina`, `orden` (fecha, relevancia,
  antiguas, nuevo, órgano). Devuelve ROJ, ECLI, órgano, fecha, ponente, resumen
  y la `url` del documento. Tarda 10-30 s.
- **`leer_sentencia`** — texto de la resolución por `url` (descarga directa en
  ~2 s, **sin navegador**) o por ROJ/ECLI. `seccion='fallo'` (o `fundamentos`,
  `antecedentes`, `hechos`, `encabezado`) devuelve solo esa parte;
  `palabras_clave='clausula suelo'` devuelve solo los párrafos que las contienen.
  `guardar_pdf` / `guardar_md` guardan además el original o un Markdown con
  metadatos y secciones. **Caché** (diskcache): la 2ª lectura es instantánea.
- **`descargar_sentencia`** — guarda PDF / MD / ambos en la carpeta que indiques
  (p.ej. la del expediente) sin volcar el texto al chat.

  > Pensado para **uso profesional propio**, consulta puntual y documento a
  > documento — **no** para descarga masiva ni para construir una base de datos
  > derivada (eso lo prohíbe el aviso legal). No se falsifican peticiones: se
  > conduce un navegador como lo haría la persona.

## Tribunal Constitucional y TJUE: texto real, sin navegador

- **`buscar_tc` / `leer_tc`** — Buscador de Jurisprudencia Constitucional oficial
  (`hj.tribunalconstitucional.es`). Sin API documentada, pero su formulario
  responde a HTTP plano sin anti-bot y cada resolución llega ya **seccionada**:
  antecedentes, fundamentos jurídicos, fallo, votos particulares, ficha técnica
  (órgano, magistrados, BOE) y extractos doctrinales. Búsqueda por texto libre
  (acotable a fundamentos/fallo), cita (`STC 31/2010`), ECLI, materia y fechas.
- **`buscar_tjue` / `leer_tjue`** — **CELLAR**, la API pública oficial de la
  Oficina de Publicaciones de la UE (la que hay detrás de EUR-Lex, que sí bloquea
  bots): SPARQL para localizar por ECLI, asunto o palabras del título, y el
  documento en **español** por CELEX. Sentencias del Tribunal de Justicia y del
  Tribunal General, conclusiones del Abogado General y autos; `seccion='fallo'`
  devuelve la parte dispositiva.

Ambos comparten con el CENDOJ `palabras_clave` (solo los párrafos relevantes),
`guardar_md` y la caché local.

**2. Respaldo offline (sin red, sin navegador):**

- **`cendoj_construir_busqueda`** — traduce lenguaje natural a los parámetros
  oficiales del buscador y devuelve la **URL exacta para abrir en tu navegador**
  + los filtros avanzados a marcar.
- **`cendoj_analizar_cita`** — verifica y descompone una cita (ECLI / ROJ /
  Id Cendoj): detecta autos (sufijo `A`), convierte ROJ↔ECLI y descompone el
  Id Cendoj. Puro parseo, sin red.
- **`estado`** — diagnóstico.

Los códigos de órgano (`common/organos.py`) y el parseo de identificadores
(`common/cendoj_ids.py`) están verificados contra el HTML y los PDF reales del
CENDOJ (ver `tests/`).

## Instalación

```bash
cd ~/iuris-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# CENDOJ en vivo necesita el navegador de Playwright (una vez):
.venv/bin/python -m playwright install chromium
```

> Variable opcional `CENDOJ_HEADLESS=false` para ver el navegador (depuración).

## Registro en Claude Code

```bash
claude mcp add iuris --scope user -- "$HOME/iuris-mcp/.venv/bin/python" "$HOME/iuris-mcp/server.py"
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Fuentes y tools (27)

**Automático — API/servicio oficial, sin captcha:**
- **BOE / legislación**: `buscar_articulo` (texto vigente consolidado), `buscar_boe`,
  `novedades_boe` (vigilancia por fechas), `sumario_boe`, `leer_boe`.
- **Catastro (OVC)**: `consultar_catastro`, `callejero_catastro`. Sin titular ni valor
  (datos protegidos); no cubre País Vasco ni Navarra (foral).
- **Mercantil (BORME)**: `sumario_borme`.
- **Fiscal DGT**: `buscar_consultas_hacienda`, `leer_consulta_hacienda`.
- **Fiscal TEAC/TEAR**: `buscar_doctrina_teac`, `leer_resolucion_teac`.
- **Convenios**: `leer_convenio` (texto desde la publicación en BOE).

**Jurisprudencia en vivo — acceso real, bajo demanda:**
- **CENDOJ**: `buscar_sentencias` (navegador), `leer_sentencia`, `descargar_sentencia` (descarga directa).
- **TC**: `buscar_tc`, `leer_tc` (HTTP plano). **TJUE/TG**: `buscar_tjue`, `leer_tjue` (CELLAR).

**Humano en el bucle — el servidor prepara la búsqueda/enlace oficial; el acceso lo
hace el usuario en su navegador (sin evasión de anti-bot):**
- **CENDOJ (respaldo offline)**: `cendoj_construir_busqueda`, `cendoj_analizar_cita`.
- **Convenios REGCON**: `buscar_convenio`, `vigencia_convenio`.
- **Empresa (RM)**: `buscar_empresa_mercantil`.
- **UE (EUR-Lex, normativa)**: `buscar_norma_ue`.

Pendiente: ordenanzas municipales (BOP fragmentado por municipio).

## Nota de seguridad (TLS de la DGT)

El servidor de PETETE (DGT) presenta una cadena TLS incompleta (omite el certificado
intermedio de la FNMT). En vez de desactivar la verificación, se **completa la cadena**
con el intermedio oficial (guardado en `common/certs/`), de modo que la verificación
TLS sigue siendo real. Ver `sources/dgt.py`.
