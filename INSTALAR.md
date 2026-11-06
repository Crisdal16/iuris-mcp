# INSTALAR — iuris-mcp (PC Windows y nube)

Guía completa de puesta en marcha. Dos escenarios:

- **PC Windows** (tu máquina): MCP stdio para Claude Code de escritorio.
- **Nube / contenedor** (Claude Code remoto): el repo se clona del GitHub y el
  agente lo ejecuta dentro de su contenedor.

## 1. Requisitos

- Python **3.11 o superior** (probado con 3.12, 3.13 y 3.14).
- Claude Code (CLI o escritorio).
- Para el CENDOJ: Chromium de Playwright (paso 3).

## 2. Instalación base

### PC Windows (PowerShell)

```powershell
cd C:\dev                       # fuera de OneDrive: evita sincronización rara
git clone https://github.com/Crisdal16/iuris-mcp.git
cd iuris-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # si bloquea la policy: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev]"
python -m playwright install chromium
```

### Nube / contenedor

El agente lo hace solo tras clonar el repo (verifica con `estado`):

```bash
pip install -e ".[dev]"
python -m playwright install chromium   # solo si el contenedor no trae Chromium
```

**Chromium en contenedor**: si pip trae una versión de Playwright cuyo build no
está en la imagen (`Executable doesn't exist at /opt/pw-browsers/...`), exporta:

```bash
export IURIS_CHROMIUM_PATH=/opt/pw-browsers/chromium   # o el binario que exista
```

`CendojBrowser` lo detecta solo. En PC no se necesita.

## 3. Validar el pool de proxies (rotación de IPs)

La rotación es **opcional** (apagada por defecto). Para usarla:

1. Crea `proxies.txt` en la raíz del repo (NO se sube al GitHub; está en
   `.gitignore`). Una IP por línea, cualquiera de estos formatos:

   ```
   # pool propio
   1.2.3.4:8080
   1.2.3.5:8080:usuario:clave
   http://usuario:clave@1.2.3.6:8080
   ```

2. Valídalo antes de empezar:

   ```bash
   python check_proxies.py          # tabla VIVA/CAIDA + IP de salida + latencia
   ```

3. Actívalo:

   - PC (permanente): `setx IURIS_ROTACION "true"` y **reabre la terminal**.
   - Nube: `export IURIS_ROTACION=true` en el entorno del contenedor.

4. Verifica con la tool `estado` del MCP:

   ```
   Rotacion de IPs: activa — 10/99 proxies en pool (...); max 5 IPs por operacion.
   ```

Ajustes finos: `IURIS_ROTACION_MAX` (IPs por operación, 5 por defecto, máx. 99)
y `IURIS_PROXIES` (otra ruta para el fichero). Una IP que falla entra en
cooldown 5 min y revive sola; sin hilos de fondo.

## 4. Registro en Claude Code

```powershell
claude mcp add iuris --scope user -- "C:\dev\iuris-mcp\.venv\Scripts\python.exe" "C:\dev\iuris-mcp\server.py"
claude mcp get iuris     # debe apuntar a esos dos paths
```

Después **reinicia Claude por completo** (en escritorio: bandeja → Salir) y
prueba: *"usa la tool estado de iuris"* → debe listar las herramientas y el
estado de la rotación.

## 5. Prueba de fuego

En una sesión de Claude:

1. `buscar_sentencias(consulta="desahogo vivienda", jurisdiccion="civil")`
2. `leer_sentencia(roj="STS 4452/2025", seccion="fallo")`
3. `descargar_sentencia(roj="...", formato="pdf")` → guarda en `descargas/`

Si el CENDOJ pide captcha a tu IP, la tool te devuelve el **enlace oficial del
PDF** para abrirlo en tu navegador (con rotación activa, antes prueba las IPs
del pool automáticamente).

## 6. Seguridad

- `proxies.txt` contiene tus credenciales: **nunca lo subas al GitHub** (ya
  está en `.gitignore`; compruébalo con `git status` antes de cualquier push).
- El modo HTTP (`server.py --http`) exige `IURIS_HTTP_TOKEN` de 32+ caracteres
  y por defecto solo escucha en 127.0.0.1.
- Las tools de CENDOJ están vedadas en modo remoto salvo
  `IURIS_CENDOJ_REMOTO=uso-profesional-propio` (uso profesional propio,
  nunca detrás de un producto comercial).

## 7. Problemas típicos

| Síntoma | Causa | Solución |
|---|---|---|
| `Executable doesn't exist at /opt/pw-browsers/...` | Build de Chromium distinto al de pip | `IURIS_CHROMIUM_PATH` al binario real |
| `ImportError: MCPServer` | mcp 1.x instalado | `pip install "mcp>=2.0,<3"` |
| `Modest backend is deprecated` | selectolax 1.x sin shim | actualiza al repo actual (shim `common/_selectolax`) |
| `No se pudo lanzar Chromium` | Falta `playwright install chromium` | ejecútalo una vez |
| `Rotacion de IPs: apagada` | Sin `IURIS_ROTACION=true` o sin `proxies.txt` | pasos de la sección 3 |
| Cita «STSJ Murcia 1791/2025» no localiza | Versiones antiguas | actualiza: ya acepta nombres de comunidad/provincia |
