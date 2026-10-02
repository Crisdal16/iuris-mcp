"""iuris-mcp — servidor MCP local de fuentes juridicas oficiales espanolas.

Arranque (stdio):  .venv/bin/python server.py

Filosofia CENDOJ: 'humano en el bucle'. El servidor prepara la busqueda y
verifica las citas; el acceso al CENDOJ lo hace el usuario en su navegador
(uso particular, sin evasion de anti-bot ni base de datos derivada). Ver
sources/cendoj.py.
"""

from __future__ import annotations

from mcp.server import MCPServer

from sources import (
    boe,
    boletines,
    calendario,
    catastro,
    cendoj,
    cendoj_live,
    deep_links,
    dgt,
    mercantil,
    regcon,
    tc,
    teac,
    tjue,
)

mcp = MCPServer(
    name="iuris-mcp",
    description="Fuentes juridicas oficiales espanolas (CENDOJ humano-en-el-bucle, BOE, Catastro).",
)


@mcp.tool()
def estado() -> str:
    """Diagnostico del servidor y de las fuentes activas."""
    return (
        "iuris-mcp — servidor MCP local de fuentes juridicas oficiales espanolas.\n\n"
        "AUTOMATICO (API/servicio oficial, sin captcha):\n"
        "  • BOE/legislacion: buscar_articulo, buscar_boe, novedades_boe, sumario_boe, leer_boe\n"
        "  • Catastro (OVC): consultar_catastro, callejero_catastro (sin titular ni valor; "
        "no cubre Pais Vasco/Navarra)\n"
        "  • Mercantil (BORME): sumario_borme\n"
        "  • Fiscal DGT: buscar_consultas_hacienda, leer_consulta_hacienda\n"
        "  • Fiscal TEAC/TEAR: buscar_doctrina_teac, leer_resolucion_teac\n"
        "  • CENDOJ (jurisprudencia): buscar_sentencias (navegador real), "
        "leer_sentencia (texto integro / seccion 'fallo' / parrafos por palabras "
        "clave), descargar_sentencia (PDF o MD al expediente). Uso profesional "
        "propio, documento a documento, no masivo.\n"
        "  • Tribunal Constitucional: buscar_tc, leer_tc (buscador HJ oficial, texto "
        "seccionado: fallo, fundamentos, votos, ficha)\n"
        "  • TJUE / Tribunal General: buscar_tjue, leer_tjue (CELLAR, API oficial de "
        "la UE; sentencias, conclusiones y autos en espanol)\n"
        "  • Convenios: leer_convenio (texto desde su publicacion en BOE)\n"
        "  • Boletines autonomicos/provinciales: leer_boletin (convenios y normas "
        "que NO estan en el BOE; por URL o por boletin+ano+numero. Conocidos: BORM)\n"
        "  • Calendario laboral: calendario_laboral (Resolucion anual del BOE; "
        "nacionales + CCAA, NO las fiestas locales) y computo_plazo (vencimientos "
        "en dias habiles o naturales)\n\n"
        "HUMANO EN EL BUCLE (el servidor prepara la busqueda/enlace oficial; el acceso "
        "lo hace el usuario en su navegador; sin evasion de anti-bot):\n"
        "  • CENDOJ (respaldo offline): cendoj_construir_busqueda, cendoj_analizar_cita\n"
        "  • Convenios REGCON: buscar_convenio, vigencia_convenio\n"
        "  • Empresa (RM): buscar_empresa_mercantil\n"
        "  • UE (EUR-Lex, normativa): buscar_norma_ue\n\n"
        "Pendiente: ordenanzas municipales (BOP fragmentado por municipio)."
    )


@mcp.tool()
def cendoj_construir_busqueda(
    consulta: str,
    base: str = "AN",
    tipo_organo: str = "",
    provincia: str = "",
    jurisdiccion: str = "",
    tipo_resolucion: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    ponente: str = "",
) -> str:
    """Prepara una busqueda de jurisprudencia en el CENDOJ para abrir en el navegador.

    Traduce lenguaje natural a los parametros oficiales del buscador (codigos de
    organo, sigla de provincia, jurisdiccion) y devuelve la URL directa mas los
    filtros avanzados a marcar. NO descarga: el acceso lo hace el usuario.

    consulta: texto libre. base: 'AN' (todo el CENDOJ), 'TS', 'TC', 'TJUE'.
    tipo_organo: 'AP','TSJ','JM'... provincia: 'Murcia','Valladolid'...
    jurisdiccion: 'CIVIL','PENAL','CONTENCIOSO','SOCIAL','MILITAR'.
    tipo_resolucion: 'SENTENCIA' o 'AUTO'. fecha_desde/hasta: dd/mm/aaaa.
    """
    return cendoj.construir_busqueda(
        consulta=consulta, base=base, tipo_organo=tipo_organo, provincia=provincia,
        jurisdiccion=jurisdiccion, tipo_resolucion=tipo_resolucion,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, ponente=ponente,
    )


@mcp.tool()
def cendoj_analizar_cita(cita: str) -> str:
    """Verifica y descompone una cita judicial (ECLI, ROJ o Id Cendoj).

    Detecta autos (sufijo 'A'), convierte ROJ<->ECLI, descompone el Id Cendoj
    (municipio/organo/seccion/anio/serial) y da el enlace del buscador para abrir
    el documento. Puro parseo offline, no toca la red.

    cita: 'STS 1177/2014', 'ECLI:ES:APB:2019:9672A', '30030330022026100387',
    'C-311/19'...
    """
    return cendoj.analizar_cita(cita)


@mcp.tool()
async def buscar_sentencias(
    consulta: str = "",
    jurisdiccion: str = "",
    localizacion: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    roj: str = "",
    ecli: str = "",
    ponente: str = "",
    norma: str = "",
    n_recurso: str = "",
    n_resolucion: str = "",
    pagina: int = 1,
    maximo: int = 10,
    orden: str = "",
) -> str:
    """Busca jurisprudencia REAL en el CENDOJ y devuelve la lista de resoluciones.

    A diferencia de cendoj_construir_busqueda (que solo prepara un enlace), esta
    tool accede al buscador con un navegador real y trae los resultados: ROJ, ECLI,
    organo, fecha, ponente, resumen y la `url` del documento (pasala a
    `leer_sentencia` para el texto integro). Uso profesional propio, bajo demanda.
    Tarda 10-30 s (navegador real).

    consulta: texto libre ('despido improcedente', 'clausula suelo').
    jurisdiccion: 'Civil','Penal','Contencioso','Social','Militar' (coma para varias).
    localizacion: CCAA o provincia ('Murcia','Cataluña','Barcelona'; coma para varias).
    fecha_desde/hasta: AAAA-MM-DD o DD/MM/AAAA. roj/ecli/ponente/norma/n_recurso/
    n_resolucion: filtros del buscador avanzado.
    maximo: resultados a devolver (hasta 50). pagina: pagina de resultados.
    orden: 'fecha' (defecto, mas recientes primero), 'relevancia', 'antiguas',
    'nuevo' (ultimas incorporadas al CENDOJ) u 'organo'.
    """
    return await cendoj_live.buscar_sentencias(
        consulta=consulta, jurisdiccion=jurisdiccion, localizacion=localizacion,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, roj=roj, ecli=ecli,
        ponente=ponente, norma=norma, n_recurso=n_recurso,
        n_resolucion=n_resolucion, pagina=pagina, maximo=maximo, orden=orden,
    )


@mcp.tool()
async def leer_sentencia(
    url: str = "",
    roj: str = "",
    ecli: str = "",
    seccion: str = "todo",
    palabras_clave: str = "",
    guardar_pdf: bool = False,
    guardar_md: bool = False,
    ruta: str = "",
    max_chars: int = 45000,
) -> str:
    """Texto de una resolucion del CENDOJ: integro, una seccion o solo los parrafos
    que tratan de algo.

    Se identifica por `url` (la que da buscar_sentencias; descarga directa en ~2 s,
    sin navegador) o por `roj`/`ecli` (se localiza primero en el buscador). Se
    cachea: la 2a lectura es instantanea.

    seccion: 'todo' (defecto), 'fallo', 'fundamentos', 'antecedentes', 'hechos',
    'encabezado'. Para leer solo lo que decide el tribunal: seccion='fallo'.
    palabras_clave: devuelve SOLO los parrafos que contienen esas palabras
    ('clausula suelo transparencia') — ideal para localizar el pasaje relevante sin
    leer 40.000 caracteres.
    guardar_pdf / guardar_md: ademas guardan el PDF original o un Markdown con
    metadatos y secciones. `ruta`: carpeta destino (defecto ./descargas del
    servidor). max_chars: limite de lo devuelto al chat (el fichero es completo).
    """
    return await cendoj_live.leer_sentencia(
        url=url, roj=roj, ecli=ecli, seccion=seccion, palabras_clave=palabras_clave,
        guardar_pdf=guardar_pdf, guardar_md=guardar_md, ruta=ruta, max_chars=max_chars,
    )


@mcp.tool()
async def descargar_sentencia(
    url: str = "",
    roj: str = "",
    ecli: str = "",
    formato: str = "pdf",
    ruta: str = "",
) -> str:
    """Guarda una resolucion del CENDOJ en disco SIN volcar su texto al chat.

    Identificala por `url` (de buscar_sentencias) o por `roj`/`ecli`.
    formato: 'pdf' (original), 'md' (Markdown con metadatos y secciones) o
    'ambos'. `ruta`: carpeta destino, p.ej. la del expediente del cliente
    (defecto ./descargas del servidor). Devuelve la ficha y las rutas guardadas.
    """
    return await cendoj_live.descargar_sentencia(
        url=url, roj=roj, ecli=ecli, formato=formato, ruta=ruta,
    )


@mcp.tool()
def buscar_articulo(ley: str, articulo: str) -> str:
    """Texto VIGENTE de un articulo de una ley espanola (legislacion consolidada del BOE).

    Fuente oficial de datos abiertos, sin captcha. Devuelve el texto integro
    vigente, la fecha de vigencia y el enlace consolidado.

    ley: sigla (LEC, CC, CP, CE, ET, LGT, LAU, LPH, LSC...), nombre completo
    ('Codigo Civil') o identificador BOE-A (BOE-A-2000-323).
    articulo: numero ('394', '1902', 'art. 138', '439 bis').
    """
    return boe.buscar_articulo(ley, articulo)


@mcp.tool()
def sumario_boe(fecha: str, seccion: str = "", contiene: str = "") -> str:
    """Que se publico en el BOE de un dia (via API oficial de datos abiertos).

    fecha: AAAA-MM-DD o DD/MM/AAAA. contiene: filtra por texto en el titulo.
    Devuelve los identificadores (BOE-A-...) para leer con leer_boe.
    """
    return boe.sumario_boe(fecha, seccion=seccion, contiene=contiene)


@mcp.tool()
def buscar_boe(consulta: str, desde: str = "", hasta: str = "", limite: int = 15) -> str:
    """Localiza legislacion (leyes, RD, ordenes...) cuyo titulo contiene la materia.

    Busca en el feed oficial de legislacion consolidada (mas reciente primero),
    con rango de fechas opcional (AAAA-MM-DD). Para el texto de un articulo usa
    buscar_articulo; para jurisprudencia, las tools cendoj_*.
    """
    return boe.buscar_boe(consulta, desde=desde, hasta=hasta, limite=limite)


@mcp.tool()
def novedades_boe(contiene: str, desde: str, hasta: str, seccion: str = "") -> str:
    """Vigila el BOE: barre los sumarios entre dos fechas (max 31 dias) y devuelve
    los items cuyo titulo contiene el texto o NIF indicado (edictos, subvenciones,
    nombramientos, anuncios sobre una empresa...). Fechas AAAA-MM-DD.
    """
    return boe.novedades_boe(contiene, desde, hasta, seccion=seccion)


@mcp.tool()
def leer_boe(identificador: str) -> str:
    """Abre una norma consolidada del BOE por su identificador (BOE-A-AAAA-N).

    Para el texto vigente de un articulo concreto usa mejor buscar_articulo.
    """
    return boe.leer_boe(identificador)


# --------------------------------------------------------------------------
# Mercantil (BORME, via API oficial de datos abiertos)
# --------------------------------------------------------------------------

@mcp.tool()
def sumario_borme(fecha: str, contiene: str = "") -> str:
    """Que se publico en el BORME de un dia (actos societarios: nombramientos,
    constituciones, disoluciones, concursos). fecha AAAA-MM-DD o DD/MM/AAAA.
    contiene: filtra por texto (p.ej. una provincia o una denominacion social).
    """
    return mercantil.sumario_borme(fecha, contiene=contiene)


@mcp.tool()
def buscar_empresa_mercantil(empresa: str) -> str:
    """Ficha registral de una sociedad por nombre o CIF (BORME / Registro Mercantil).

    El BORME solo se indexa por fecha, no hay busqueda abierta por nombre: la tool
    prepara los buscadores oficiales para que los abras (indice sin fe publica,
    sin cuentas anuales).
    """
    return mercantil.buscar_empresa_mercantil(empresa)


# --------------------------------------------------------------------------
# Catastro (servicios OVC oficiales de la Direccion General del Catastro)
# --------------------------------------------------------------------------

@mcp.tool()
def consultar_catastro(referencia_catastral: str = "", direccion: str = "",
                       municipio: str = "", provincia: str = "", poligono: str = "",
                       parcela: str = "", coordenadas: str = "", sigla: str = "",
                       numero: str = "") -> str:
    """Datos catastrales NO protegidos de un inmueble o finca (DG del Catastro).

    Identifica por referencia_catastral (14/20 car.), direccion+municipio,
    poligono+parcela+municipio (rustica) o coordenadas 'lat,lon'. Devuelve
    superficie, uso, antiguedad, plantas, localizacion y referencia. NO da titular
    ni valor catastral (protegidos). No cubre Pais Vasco ni Navarra (foral).
    """
    return catastro.consultar_catastro(
        referencia_catastral=referencia_catastral, direccion=direccion,
        municipio=municipio, provincia=provincia, poligono=poligono,
        parcela=parcela, coordenadas=coordenadas, sigla=sigla, numero=numero,
    )


@mcp.tool()
def callejero_catastro(municipio: str = "", provincia: str = "", via: str = "",
                       numero: str = "") -> str:
    """Callejero del Catastro: provincias, municipios o vias, para desambiguar
    una direccion. Sin args lista provincias; con provincia, sus municipios; con
    via, las vias que coinciden en ese municipio.
    """
    return catastro.callejero_catastro(municipio=municipio, provincia=provincia, via=via, numero=numero)


# --------------------------------------------------------------------------
# Convenios colectivos (REGCON: busqueda HITL; lectura del texto desde BOE)
# --------------------------------------------------------------------------

@mcp.tool()
def buscar_convenio(consulta: str, territorio: str = "", ambito: str = "sector",
                    maximo: int = 8) -> str:
    """Localiza el convenio colectivo de un sector y territorio (registro REGCON).

    El buscador de REGCON exige sesion con JavaScript, asi que la tool prepara la
    busqueda oficial (con el territorio y ambito ya traducidos) para que la abras.
    Si ya tienes el BOE-A de su publicacion, usa leer_convenio directamente.
    """
    return regcon.buscar_convenio(consulta, territorio=territorio, ambito=ambito, maximo=maximo)


@mcp.tool()
def leer_convenio(codigo: str = "", consulta: str = "", territorio: str = "",
                  articulo: str = "") -> str:
    """Texto oficial de un convenio colectivo desde su publicacion en el BOE.

    codigo: identificador BOE-A de la publicacion (automatico) o codigo REGCON de
    14 digitos / texto libre (redirige a la busqueda). articulo: devuelve solo ese
    articulo si se indica.
    """
    return regcon.leer_convenio(codigo=codigo, consulta=consulta, territorio=territorio, articulo=articulo)


@mcp.tool()
def vigencia_convenio(codigo: str) -> str:
    """Estado de vigencia y tramites de un convenio (codigo REGCON de 14 digitos)."""
    return regcon.vigencia_convenio(codigo)


# --------------------------------------------------------------------------
# Boletines autonomicos y provinciales (BORM, BOP...)
# --------------------------------------------------------------------------

@mcp.tool()
def leer_boletin(url: str = "", boletin: str = "", ano: str = "", numero: str = "",
                 articulo: str = "", max_chars: int = 14000) -> str:
    """Texto oficial de una disposicion de un boletin AUTONOMICO o PROVINCIAL.

    Usala cuando la norma NO este en el BOE: convenios colectivos autonomicos y
    provinciales, ordenanzas, calendarios de fiestas locales... `leer_convenio`
    solo cubre lo publicado en el BOE; esta tool cubre el resto.

    Se le da la URL oficial del documento (PDF o HTML), o bien un boletin
    conocido («borm») con `ano` y `numero` de anuncio. Con `articulo` devuelve
    solo ese articulo.
    """
    return boletines.leer_boletin(url=url, boletin=boletin, ano=ano, numero=numero,
                                  articulo=articulo, max_chars=max_chars)


# --------------------------------------------------------------------------
# Calendario laboral y computo de plazos
# --------------------------------------------------------------------------

@mcp.tool()
def calendario_laboral(anio: int, comunidad: str = "") -> str:
    """Fiestas laborales de un ano, segun la Resolucion anual publicada en el BOE.

    `comunidad`: nombre de la CCAA (p.ej. «Murcia», «Andalucia»). Sin ella,
    devuelve solo las nacionales. NO incluye las dos fiestas locales de cada
    municipio, que publica el boletin autonomico.
    """
    return calendario.calendario_laboral(anio, comunidad)


@mcp.tool()
def computo_plazo(desde: str, dias: int, comunidad: str = "",
                  festivos_locales: str = "", naturales: bool = False) -> str:
    """Calcula el vencimiento de un plazo procesal o sustantivo.

    `desde`: dia inicial del computo (dd/mm/aaaa), ya determinado por quien
    llama (p.ej. el dia siguiente al despido). `dias`: numero de dias.
    En dias habiles excluye sabados, domingos y festivos oficiales de la
    comunidad. `festivos_locales`: fechas adicionales separadas por comas
    (las dos fiestas del municipio). `naturales=True` para plazos en dias
    naturales.
    """
    return calendario.computo_plazo(desde, dias, comunidad=comunidad,
                                    festivos_locales=festivos_locales,
                                    naturales=naturales)


# --------------------------------------------------------------------------
# Fiscal: DGT (consultas de Hacienda) y TEAC/TEAR (doctrina economico-adva)
# --------------------------------------------------------------------------

@mcp.tool()
def buscar_consultas_hacienda(consulta: str = "", numero: str = "", normativa: str = "",
                              desde: str = "", hasta: str = "", tipo: str = "vinculantes",
                              limite: int = 15) -> str:
    """Doctrina de la DGT: consultas vinculantes/generales de Hacienda sobre tributos.

    consulta: texto libre (respeta las tildes: el buscador de la DGT es sensible a
    acentos). numero: 'V0282-26'. tipo: 'vinculantes' (defecto) o 'generales'.
    Para el texto integro de una: leer_consulta_hacienda(numero).
    """
    return dgt.buscar_consultas_hacienda(consulta=consulta, numero=numero, normativa=normativa,
                                         desde=desde, hasta=hasta, tipo=tipo, limite=limite)


@mcp.tool()
def leer_consulta_hacienda(numero: str) -> str:
    """Texto integro de una consulta de la DGT por su numero (p.ej. 'V0282-26')."""
    return dgt.leer_consulta_hacienda(numero)


@mcp.tool()
def buscar_doctrina_teac(consulta: str = "", frase: str = "", numero_rg: str = "",
                         organo: str = "TEAC", desde: str = "", hasta: str = "",
                         maximo: int = 10) -> str:
    """Doctrina y criterios del TEAC/TEAR (via administrativa previa al contencioso).

    consulta: texto libre. frase: frase exacta (mas precisa; el buscador no filtra
    en AND estricto). numero_rg: '00/06291/2024'. organo: 'TEAC' (defecto) o un TEAR.
    Para la ficha + texto integro: leer_resolucion_teac(numero_rg).
    """
    return teac.buscar_doctrina_teac(consulta=consulta, frase=frase, numero_rg=numero_rg,
                                     organo=organo, desde=desde, hasta=hasta, maximo=maximo)


@mcp.tool()
def leer_resolucion_teac(numero_rg: str) -> str:
    """Ficha doctrinal + texto integro de una resolucion del TEAC/TEAR por su RG."""
    return teac.leer_resolucion_teac(numero_rg)


# --------------------------------------------------------------------------
# Normativa UE / TC / TJUE (humano en el bucle: enlace oficial preparado)
# --------------------------------------------------------------------------

@mcp.tool()
def buscar_norma_ue(referencia: str, articulo: str = "") -> str:
    """Prepara el enlace EUR-Lex (texto consolidado en espanol) de una norma UE.

    referencia: 'RGPD', 'Directiva 93/13/CEE', 'Reglamento (UE) 2016/679' o el
    CELEX directo ('32016R0679'). EUR-Lex aplica anti-bot, asi que el enlace lo
    abres tu.
    """
    return deep_links.norma_ue(referencia, articulo=articulo)


@mcp.tool()
def buscar_tc(consulta: str = "", ambito: str = "todo", numero: str = "", anio: str = "",
              ecli: str = "", tipo: str = "", materia: str = "", fecha_desde: str = "",
              fecha_hasta: str = "", pagina: int = 1, maximo: int = 10) -> str:
    """Busca en el Buscador de Jurisprudencia Constitucional (TC) y devuelve resultados
    REALES con su sintesis (sin navegador; fuente oficial hj.tribunalconstitucional.es).

    consulta: texto libre ('clausula suelo tutela judicial') o una cita ('STC 31/2010').
    ambito: donde buscar el texto libre: 'todo' (defecto), 'fundamentos', 'fallo',
    'antecedentes', 'votos', 'sintesis'. numero+anio: '31' + '2010'. ecli:
    'ECLI:ES:TC:2010:31'. tipo: 'sentencia'|'auto'|'declaracion'. materia: 'civil',
    'penal', 'social', 'contencioso', 'electoral', 'parlamentario', 'militar'.
    fecha_desde/hasta: AAAA-MM-DD o DD/MM/AAAA. Cada resultado trae un `id` para leer_tc.
    """
    return tc.buscar_tc(consulta=consulta, ambito=ambito, numero=numero, anio=anio, ecli=ecli,
                        tipo=tipo, materia=materia, fecha_desde=fecha_desde,
                        fecha_hasta=fecha_hasta, pagina=pagina, maximo=maximo)


@mcp.tool()
def leer_tc(referencia: str, seccion: str = "todo", palabras_clave: str = "",
            guardar_md: bool = False, ruta: str = "", max_chars: int = 45000) -> str:
    """Texto de una resolucion del Tribunal Constitucional, ya seccionado.

    referencia: el `id` de buscar_tc, la cita ('STC 31/2010', 'ATC 12/2020') o el
    ECLI ('ECLI:ES:TC:2019:76'). seccion: 'todo', 'fallo', 'fundamentos',
    'antecedentes', 'votos', 'ficha' (organo, magistrados, ponente, BOE),
    'extractos' (sintesis doctrinal). palabras_clave: solo los parrafos que las
    contienen. guardar_md: guarda un Markdown completo por secciones en `ruta`.
    Ojo: algunas STC son enormes (la 31/2010 supera 2 M de caracteres): usa
    seccion o palabras_clave.
    """
    return tc.leer_tc(referencia, seccion=seccion, palabras_clave=palabras_clave,
                      guardar_md=guardar_md, ruta=ruta, max_chars=max_chars)


@mcp.tool()
def buscar_tjue(consulta: str, desde: str = "", hasta: str = "", tribunal: str = "",
                maximo: int = 10) -> str:
    """Busca jurisprudencia del TJUE / Tribunal General via CELLAR (API publica
    oficial de la Oficina de Publicaciones de la UE), en espanol y sin navegador.

    consulta: palabras del TITULO/descriptores ('cláusulas abusivas consumidor',
    con tildes), un asunto ('C-311/18': lista sentencia, conclusiones y autos) o un
    ECLI ('ECLI:EU:C:2020:559'). desde/hasta: AAAA-MM-DD. tribunal: '' (ambos),
    'justicia' o 'general'. Devuelve ECLI, fecha, asunto, titulo y CELEX (para leer_tjue).
    """
    return tjue.buscar_tjue(consulta, desde=desde, hasta=hasta, tribunal=tribunal, maximo=maximo)


@mcp.tool()
def leer_tjue(referencia: str, tipo: str = "sentencia", seccion: str = "todo",
              palabras_clave: str = "", guardar_md: bool = False, ruta: str = "",
              max_chars: int = 45000) -> str:
    """Texto en ESPANOL de una sentencia, auto o conclusiones del TJUE / Tribunal
    General (CELLAR, fuente oficial).

    referencia: asunto ('C-311/18', 'T-778/16'), ECLI ('ECLI:EU:C:2020:559') o
    CELEX ('62018CJ0311'). tipo: 'sentencia' (defecto), 'conclusiones' (del
    Abogado General) o 'auto'. seccion: 'todo' o 'fallo' (parte dispositiva).
    palabras_clave: solo los parrafos que las contienen. guardar_md: guarda el
    texto completo en `ruta`.
    """
    return tjue.leer_tjue(referencia, tipo=tipo, seccion=seccion, palabras_clave=palabras_clave,
                          guardar_md=guardar_md, ruta=ruta, max_chars=max_chars)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
