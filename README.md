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

## Modo remoto (HTTP)

El modo por defecto sigue siendo **stdio** (Claude Code; su configuración no cambia).
Para que otro servicio propio consulte iuris por red —p. ej. el auditor de demandas
de monitorio-ia a través del conector MCP de la API de Claude— hay un modo
**streamable-http** con token Bearer obligatorio (código en `common/remoto.py`).

```bash
export IURIS_HTTP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
<venv>/python server.py --http                       # 127.0.0.1:8790, endpoint /mcp
<venv>/python server.py --http --host 127.0.0.1 --port 8790 --tools auditor
IURIS_TRANSPORT=http <venv>/python server.py         # equivalente a --http
```

| Variable / flag | Efecto |
|---|---|
| `IURIS_HTTP_TOKEN` | **Obligatoria.** Token(s) Bearer, separados por comas, de 32 caracteres o más. Sin ella el modo HTTP no arranca. Comparación en tiempo constante; sin token o con uno erróneo → `401`. |
| `IURIS_TRANSPORT=http` / `--http` | Activa el modo HTTP. |
| `IURIS_HTTP_HOST` / `--host` | Interfaz. Por defecto `127.0.0.1` (solo local; para exponerlo, proxy inverso con HTTPS). |
| `IURIS_HTTP_PORT` / `--port` | Puerto. Por defecto `8790`. |
| `IURIS_HTTP_PATH` / `--path` | Ruta del endpoint MCP. Por defecto `/mcp`. `GET /salud` responde `ok` sin token (para el proxy). |
| `IURIS_TOOLS` / `--tools` | `auditor` (por defecto): `buscar_articulo`, `buscar_boe`, `leer_boe`, `buscar_por_cita`, `verificar_escrito`, `computo_plazo`, `calendario_laboral` y `continuar_lectura`. `todas`: todas salvo CENDOJ. O una lista separada por comas. |
| `IURIS_HTTP_RPM` / `--rpm` | Peticiones por minuto y token (por defecto 60; `0` = sin límite). Al pasarse → `429` con `Retry-After`. |
| `IURIS_ALLOWED_HOSTS` | Nombre(s) públicos con los que llega el proxy (`iuris.midominio.es`). La librería rechaza con `421` cualquier otro `Host` (anti DNS-rebinding). |
| `IURIS_CENDOJ_REMOTO=uso-profesional-propio` / `--cendoj-uso-profesional-propio` | Ver «CENDOJ en remoto». |

Además, en modo HTTP:
- Las tools **no leen ni guardan ficheros del servidor** (`verificar_escrito` solo con
  `texto`; nada de `ruta` ni `guardar_*`).
- Respuestas JSON sin estado (`stateless_http`, `json_response`), cuerpo de petición
  de 2 MB como máximo; los textos largos ya salen recortados por `common.lecturas`
  (el resto con `continuar_lectura`).

### CENDOJ en remoto: siempre fuera

El aviso legal del CENDOJ no permite «la utilización de la base de datos para usos
comerciales, ni la descarga masiva»; la reutilización comercial va por el
procedimiento del CGPJ (Ley 37/2007, LRISP). Como el modo remoto lo usará un
**producto de pago**, en HTTP las tools de CENDOJ (`buscar_sentencias`,
`leer_sentencia`, `descargar_sentencia`, `cendoj_*`) quedan **siempre fuera, aunque se
pida `todas`**, y `buscar_por_cita` / `verificar_escrito` tampoco consultan el CENDOJ
(devuelven un aviso y el enlace a poderjudicial.es; las STS/SAP de un escrito salen
«sin comprobar»). Solo se reactivan con `IURIS_CENDOJ_REMOTO=uso-profesional-propio`
(o `--cendoj-uso-profesional-propio`), **exclusivamente para uso profesional propio,
nunca detrás de monitorio-ia ni de otro servicio comercial**. Además necesitaría
Chromium en el servidor.

### Despliegue (ejemplos; no desplegado)

Unidad systemd (`/etc/systemd/system/iuris-mcp.service`):

```ini
[Unit]
Description=iuris-mcp (modo HTTP)
After=network-online.target

[Service]
User=iuris
WorkingDirectory=/opt/iuris-mcp
EnvironmentFile=/etc/iuris-mcp.env
ExecStart=/opt/iuris-mcp/.venv/bin/python server.py --http --host 127.0.0.1 --port 8790
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/opt/iuris-mcp/.cache

[Install]
WantedBy=multi-user.target
```

`/etc/iuris-mcp.env` (permisos `600`, propietario root):

```bash
IURIS_HTTP_TOKEN=<token aleatorio de 32+ caracteres>
IURIS_TOOLS=auditor
IURIS_HTTP_RPM=60
IURIS_ALLOWED_HOSTS=iuris.midominio.es
```

Proxy inverso con HTTPS — Caddy (`/etc/caddy/Caddyfile`, certificado automático):

```caddy
iuris.midominio.es {
    reverse_proxy 127.0.0.1:8790
}
```

o Nginx (con certbot):

```nginx
server {
    listen 443 ssl http2;
    server_name iuris.midominio.es;
    ssl_certificate     /etc/letsencrypt/live/iuris.midominio.es/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/iuris.midominio.es/privkey.pem;
    client_max_body_size 2m;
    location / {
        proxy_pass http://127.0.0.1:8790;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 180s;
        proxy_buffering off;
    }
}
```

### Cómo lo usa monitorio-ia (conector MCP de la API de Claude)

El conector lo llama desde los servidores de Anthropic, así que la URL debe ser
pública y con HTTPS (no sirve `127.0.0.1`). El token vive solo en el servidor de
monitorio-ia (`IURIS_MCP_TOKEN`), nunca en el navegador:

```ts
const respuesta = await anthropic.beta.messages.create({
  model: process.env.AUDITOR_MODEL!,      // el modelo que use el auditor
  max_tokens: 4096,
  betas: ["mcp-client-2025-11-20"],
  mcp_servers: [{
    type: "url",
    url: "https://iuris.midominio.es/mcp",
    name: "iuris",
    authorization_token: process.env.IURIS_MCP_TOKEN,
  }],
  tools: [{
    type: "mcp_toolset",
    mcp_server_name: "iuris",
    default_config: { enabled: false },   // lista blanca: solo lo que usa el auditor
    configs: {
      buscar_articulo: { enabled: true },
      buscar_por_cita: { enabled: true },
      verificar_escrito: { enabled: true },
      computo_plazo: { enabled: true },
    },
  }],
  messages: [{ role: "user", content: "Verifica en el BOE los artículos citados en esta demanda: …" }],
});
```

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
