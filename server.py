"""iuris-mcp — servidor MCP local de fuentes juridicas oficiales espanolas y de la UE.

Arranque (stdio):  <venv>/python server.py
Modo remoto:       IURIS_HTTP_TOKEN=... <venv>/python server.py --http  (ver common/remoto.py)

Tres regimenes de acceso (ver README):
  * API/servicio oficial abierto (BOE, Catastro, BORME, DGT, TEAC, TC, CELLAR):
    automatico, sin captcha.
  * CENDOJ: navegador real para BUSCAR, documento a documento, uso profesional
    propio (no masivo); la LECTURA va por descarga directa.
  * Humano en el bucle (REGCON, Registro Mercantil, BOP de ordenanzas): el
    servidor prepara la busqueda oficial y el usuario la abre.

Todas las tools son de lectura. Las unicas que escriben en disco son las de
guardar/descargar una resolucion, y solo en la carpeta indicada.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from common import lecturas
from sources import (
    boe,
    boletines,
    calendario,
    catastro,
    cendoj,
    cendoj_live,
    deep_links,
    dgt,
    escritos,
    mercantil,
    normativa_ue,
    ordenanzas,
    regcon,
    tc,
    teac,
    tjue,
    verificacion,
)
from common.citas import es_norma_ue

# Una linea de log por peticion HTTP solo ensucia el log del MCP (va a stderr).
logging.getLogger("httpx").setLevel(logging.WARNING)

INSTRUCCIONES = """\
iuris da acceso a fuentes OFICIALES del Derecho espanol y de la UE. Usalo siempre que haga \
falta una norma, una resolucion o una publicacion oficial; no cites de memoria lo que puedas \
comprobar aqui.

Como elegir:
• Texto VIGENTE de un articulo (leyes espanolas, incluidas disposiciones adicionales/\
transitorias, y reglamentos o directivas UE) → buscar_articulo. Acepta siglas (LEC, CC, ET, \
LGT, LOPDGDD…), 'Ley 29/1998', 'LO 3/2018', BOE-A-… y 'RGPD' / 'Directiva 93/13/CEE'.
• Localizar normas por materia → buscar_boe. Que salio en el BOE un dia → sumario_boe; \
vigilar un periodo → novedades_boe. BORME de un dia → sumario_borme.
• Cualquier cita concreta (STC 31/2010, STS 1177/2014, ECLI, C-311/18, art. 1902 CC, \
V0282-26, RG 00/06291/2024, BOE-A-…) → buscar_por_cita, que la abre en su fuente.
• Jurisprudencia por tema: CENDOJ (TS, AN, TSJ, AP, juzgados) → buscar_sentencias + \
leer_sentencia; Tribunal Constitucional → buscar_tc + leer_tc; TJUE/Tribunal General → \
buscar_tjue + leer_tjue. Usa seccion='fallo' o palabras_clave para no leer textos enteros.
• Doctrina tributaria: DGT → buscar_consultas_hacienda / leer_consulta_hacienda; TEAC/TEAR → \
buscar_doctrina_teac / leer_resolucion_teac.
• Convenios colectivos → buscar_convenio, leer_convenio, vigencia_convenio; los publicados \
en boletines autonomicos o provinciales → leer_boletin.
• Ordenanzas municipales → buscar_ordenanzas (+ leer_boletin con la URL del anuncio).
• Catastro → consultar_catastro / callejero_catastro. Empresas → buscar_empresa_mercantil.
• Plazos → calendario_laboral y computo_plazo.
• Redactar un escrito → guia_escrito PRIMERO; revisar las citas de un borrador → \
verificar_escrito.
• Si una respuesta acaba en 'continuar_lectura(lectura=…, desde=…)', pide el siguiente tramo \
solo si lo necesitas.

Si una fuente responde que el servidor oficial esta caido (HTTP 5xx), dilo y no reintentes en \
bucle. CENDOJ: uso profesional propio, documento a documento; no hagas barridos masivos.
"""

mcp = MCPServer(
    name="iuris-mcp",
    title="iuris — fuentes juridicas oficiales",
    description="BOE, CENDOJ, Tribunal Constitucional, TJUE, normativa UE, DGT, TEAC, "
                "Catastro, BORME, convenios, boletines y ordenanzas.",
    instructions=INSTRUCCIONES,
    version="0.2.0",
)


def herramienta(titulo: str, *, red: bool = True, escribe: bool = False):
    """@mcp.tool con anotaciones y SIN salida estructurada: las tools devuelven
    texto, y el envoltorio {'result': ...} duplicaria cada respuesta en el contexto."""
    return mcp.tool(
        title=titulo,
        structured_output=False,
        annotations=ToolAnnotations(
            title=titulo,
            readOnlyHint=not escribe,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=red,
        ),
    )


# --------------------------------------------------------------------------
# Diagnostico y utilidades
# --------------------------------------------------------------------------

@herramienta("Estado del servidor", red=False)
def estado() -> str:
    """Diagnostico: version, fuentes y lista de herramientas disponibles."""
    tools = sorted(mcp._tool_manager.list_tools(), key=lambda t: t.name)
    lineas = [f"iuris-mcp {mcp.version} — {len(tools)} herramientas", ""]
    for t in tools:
        desc = " ".join((t.description or "").split())
        frase = desc.split(". ", 1)[0].rstrip(".")
        if len(frase) > 120:
            frase = frase[:117].rsplit(" ", 1)[0] + "…"
        lineas.append(f"  • {t.name}: {frase}")
    lineas += ["", "Fuentes: BOE (API datos abiertos), CENDOJ (navegador para buscar, descarga "
               "directa para leer), TC (hj.tribunalconstitucional.es), TJUE y normativa UE "
               "(CELLAR), DGT (PETETE), TEAC (DYCTEA), Catastro (OVC), BORME, REGCON, "
               "boletines autonomicos/provinciales."]
    return "\n".join(lineas)


@herramienta("Continuar lectura", red=False)
def continuar_lectura(lectura: str, desde: int = 0, max_chars: int = 30000) -> str:
    """Siguiente tramo de un texto largo que otra herramienta recorto.

    Cuando una respuesta acaba en 'continuar_lectura(lectura='abc123', desde=45000)',
    llama con esos valores para seguir leyendo sin volver a descargar. Las lecturas
    caducan a los 7 dias.
    """
    return lecturas.tramo(lectura, desde, max_chars)


@herramienta("Abrir una cita")
async def buscar_por_cita(cita: str, seccion: str = "todo", palabras_clave: str = "",
                          max_chars: int = 30000) -> str:
    """Abre CUALQUIER cita juridica en su fuente oficial, detectando de que tipo es.

    cita: 'STC 31/2010', 'STS 1177/2014', 'SAP VA 863/2026', 'ECLI:ES:TS:2014:4786',
    'C-311/18', 'ECLI:EU:C:2020:559', 'art. 1902 CC', 'articulo 46 de la Ley 29/1998',
    'art. 17 RGPD', 'Ley 29/1998', 'Directiva 93/13/CEE', 'BOE-A-2000-323', 'V0282-26'
    (DGT), '00/06291/2024' (TEAC).
    seccion / palabras_clave: para resoluciones judiciales, como en leer_sentencia.
    Ojo: 'STS 1177/2014' se interpreta como ROJ; si es el numero de resolucion, busca
    con buscar_sentencias.
    """
    return await verificacion.buscar_por_cita(cita, seccion=seccion,
                                              palabras_clave=palabras_clave,
                                              max_chars=max_chars)


@herramienta("Verificar las citas de un escrito")
async def verificar_escrito(texto: str = "", ruta: str = "", comprobar_cendoj: bool = False,
                            max_cendoj: int = 3, incluir_texto: bool = False) -> str:
    """Extrae TODAS las citas de un escrito (articulos con su norma, STS/STC/ROJ, ECLI,
    asuntos del TJUE, BOE-A, consultas DGT, RG del TEAC) y comprueba cada una en su
    fuente oficial: si existe, si el articulo esta derogado y que redaccion esta vigente.

    Devuelve un dossier con la frase del escrito que invoca cada cita y el texto oficial,
    para que compares lo que el escrito AFIRMA con lo que la norma o sentencia DICE.
    texto: el escrito pegado. ruta: alternativa, fichero .docx, .pdf, .md o .txt.
    comprobar_cendoj: consultar tambien las sentencias del CENDOJ (navegador, 10-30 s
    cada una; como mucho max_cendoj). incluir_texto: texto integro en vez de extractos.
    """
    return await verificacion.verificar_escrito(texto=texto, ruta=ruta,
                                                comprobar_cendoj=comprobar_cendoj,
                                                max_cendoj=max_cendoj,
                                                incluir_texto=incluir_texto)


@herramienta("Guia para redactar un escrito")
def guia_escrito(escrito: str = "", jurisdiccion: str = "", verificar: bool = True) -> str:
    """Metodo para redactar un escrito: preguntas previas, estructura, plazos,
    documentos y errores tipicos, con su base legal VIGENTE comprobada en el BOE.

    Llamala ANTES de redactar una demanda, contestacion, recurso, monitorio,
    demanda de despido, recurso contencioso o administrativo, querella...
    escrito: id ('demanda-juicio-verbal') o descripcion ('recurso de apelacion').
    Vacio = catalogo. jurisdiccion: 'civil', 'laboral', 'contencioso', 'penal'.
    verificar=False omite la consulta al BOE (mas rapido).
    """
    return escritos.guia_escrito(escrito, jurisdiccion=jurisdiccion, verificar=verificar)


# --------------------------------------------------------------------------
# Jurisprudencia: CENDOJ
# --------------------------------------------------------------------------

@herramienta("Preparar busqueda en el CENDOJ (sin red)", red=False)
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
    """Respaldo offline: prepara la URL y los filtros del buscador del CENDOJ para abrirlos
    en el navegador. Usala solo si buscar_sentencias falla.

    consulta: texto libre. base: 'AN' (todo el CENDOJ), 'TS'. tipo_organo: 'AP','TSJ',
    'JM'... provincia: 'Murcia'... jurisdiccion: 'CIVIL','PENAL','CONTENCIOSO','SOCIAL',
    'MILITAR'. tipo_resolucion: 'SENTENCIA' o 'AUTO'. fechas: dd/mm/aaaa.
    """
    return cendoj.construir_busqueda(
        consulta=consulta, base=base, tipo_organo=tipo_organo, provincia=provincia,
        jurisdiccion=jurisdiccion, tipo_resolucion=tipo_resolucion,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, ponente=ponente,
    )


@herramienta("Analizar una cita judicial (sin red)", red=False)
def cendoj_analizar_cita(cita: str) -> str:
    """Descompone una cita judicial (ECLI, ROJ o Id Cendoj) sin tocar la red: detecta
    autos (sufijo 'A'), convierte ROJ<->ECLI y descompone el Id Cendoj. Para LEER la
    resolucion usa buscar_por_cita.
    """
    return cendoj.analizar_cita(cita)


@herramienta("Buscar jurisprudencia (CENDOJ)")
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
    """Busca jurisprudencia en el CENDOJ (TS, AN, TSJ, AP, juzgados) y devuelve ROJ, ECLI,
    organo, fecha, ponente, resumen y la `url` para leer_sentencia. Tarda 10-30 s
    (navegador real). Para el TC usa buscar_tc; para el TJUE, buscar_tjue.

    consulta: texto libre ('despido improcedente', 'clausula suelo').
    jurisdiccion: 'Civil','Penal','Contencioso','Social','Militar' (coma para varias).
    localizacion: CCAA o provincia ('Murcia','Cataluña','Barcelona').
    fecha_desde/hasta: AAAA-MM-DD o DD/MM/AAAA. roj/ecli/ponente/norma/n_recurso/
    n_resolucion: filtros avanzados. maximo: hasta 50. pagina: pagina de resultados.
    orden: 'fecha' (defecto), 'relevancia', 'antiguas', 'nuevo' u 'organo'.
    """
    return await cendoj_live.buscar_sentencias(
        consulta=consulta, jurisdiccion=jurisdiccion, localizacion=localizacion,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, roj=roj, ecli=ecli,
        ponente=ponente, norma=norma, n_recurso=n_recurso,
        n_resolucion=n_resolucion, pagina=pagina, maximo=maximo, orden=orden,
    )


@herramienta("Leer una sentencia (CENDOJ)", escribe=True)
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
    """Texto de una resolucion del CENDOJ: integra, una seccion o solo los parrafos que
    tratan de algo. Se identifica por `url` (de buscar_sentencias; ~2 s) o por roj/ecli.

    seccion: 'todo', 'fallo', 'fundamentos', 'antecedentes', 'hechos', 'encabezado'.
    palabras_clave: solo los parrafos que las contienen ('clausula suelo transparencia').
    guardar_pdf / guardar_md: guarda tambien el PDF original o un Markdown en `ruta`
    (carpeta del expediente; defecto ./descargas). max_chars: tope de lo devuelto; el
    resto queda disponible con continuar_lectura.
    """
    return await cendoj_live.leer_sentencia(
        url=url, roj=roj, ecli=ecli, seccion=seccion, palabras_clave=palabras_clave,
        guardar_pdf=guardar_pdf, guardar_md=guardar_md, ruta=ruta, max_chars=max_chars,
    )


@herramienta("Descargar una sentencia al expediente", escribe=True)
async def descargar_sentencia(
    url: str = "",
    roj: str = "",
    ecli: str = "",
    formato: str = "pdf",
    ruta: str = "",
) -> str:
    """Guarda una resolucion del CENDOJ en disco SIN volcar su texto al chat.

    url (de buscar_sentencias) o roj/ecli. formato: 'pdf', 'md' o 'ambos'.
    ruta: carpeta destino (p.ej. la del expediente; defecto ./descargas).
    """
    return await cendoj_live.descargar_sentencia(
        url=url, roj=roj, ecli=ecli, formato=formato, ruta=ruta,
    )


# --------------------------------------------------------------------------
# Jurisprudencia: Tribunal Constitucional y TJUE
# --------------------------------------------------------------------------

@herramienta("Buscar jurisprudencia constitucional (TC)")
def buscar_tc(consulta: str = "", ambito: str = "todo", numero: str = "", anio: str = "",
              ecli: str = "", tipo: str = "", materia: str = "", fecha_desde: str = "",
              fecha_hasta: str = "", pagina: int = 1, maximo: int = 10) -> str:
    """Busca en el Buscador de Jurisprudencia Constitucional (STC/ATC/DTC desde 1980) y
    devuelve resultados con su sintesis y un `id` para leer_tc.

    consulta: texto libre o cita ('STC 31/2010'). ambito: 'todo', 'fundamentos', 'fallo',
    'antecedentes', 'votos', 'sintesis'. numero+anio, ecli ('ECLI:ES:TC:2010:31').
    tipo: 'sentencia'|'auto'|'declaracion'. materia: 'civil', 'penal', 'social',
    'contencioso', 'electoral', 'parlamentario', 'militar'. Fechas AAAA-MM-DD.
    """
    return tc.buscar_tc(consulta=consulta, ambito=ambito, numero=numero, anio=anio, ecli=ecli,
                        tipo=tipo, materia=materia, fecha_desde=fecha_desde,
                        fecha_hasta=fecha_hasta, pagina=pagina, maximo=maximo)


@herramienta("Leer una resolucion del TC", escribe=True)
def leer_tc(referencia: str, seccion: str = "todo", palabras_clave: str = "",
            guardar_md: bool = False, ruta: str = "", max_chars: int = 45000) -> str:
    """Texto de una resolucion del Tribunal Constitucional, ya seccionado.

    referencia: `id` de buscar_tc, cita ('STC 31/2010', 'ATC 12/2020') o ECLI.
    seccion: 'todo', 'fallo', 'fundamentos', 'antecedentes', 'votos', 'ficha',
    'extractos'. palabras_clave: solo los parrafos que las contienen. guardar_md: guarda
    el Markdown completo en `ruta`. Algunas STC son enormes: acota con seccion.
    """
    return tc.leer_tc(referencia, seccion=seccion, palabras_clave=palabras_clave,
                      guardar_md=guardar_md, ruta=ruta, max_chars=max_chars)


@herramienta("Buscar jurisprudencia del TJUE")
def buscar_tjue(consulta: str, desde: str = "", hasta: str = "", tribunal: str = "",
                maximo: int = 10) -> str:
    """Busca sentencias del TJUE y del Tribunal General (CELLAR, fuente oficial, en espanol).

    consulta: palabras del titulo con tildes ('cláusulas abusivas consumidor'), un asunto
    ('C-311/18': sentencia, conclusiones y autos) o un ECLI. desde/hasta: AAAA-MM-DD.
    tribunal: '' (ambos), 'justicia' o 'general'. Devuelve ECLI, asunto y CELEX.
    """
    return tjue.buscar_tjue(consulta, desde=desde, hasta=hasta, tribunal=tribunal, maximo=maximo)


@herramienta("Leer una resolucion del TJUE", escribe=True)
def leer_tjue(referencia: str, tipo: str = "sentencia", seccion: str = "todo",
              palabras_clave: str = "", guardar_md: bool = False, ruta: str = "",
              max_chars: int = 45000) -> str:
    """Texto en espanol de una sentencia, auto o conclusiones del TJUE / Tribunal General.

    referencia: asunto ('C-311/18'), ECLI o CELEX. tipo: 'sentencia', 'conclusiones'
    (Abogado General) o 'auto'. seccion: 'todo' o 'fallo'. palabras_clave: solo los
    parrafos que las contienen. guardar_md: texto completo en `ruta`.
    """
    return tjue.leer_tjue(referencia, tipo=tipo, seccion=seccion, palabras_clave=palabras_clave,
                          guardar_md=guardar_md, ruta=ruta, max_chars=max_chars)


# --------------------------------------------------------------------------
# Legislacion: BOE y UE
# --------------------------------------------------------------------------

@herramienta("Texto vigente de un articulo")
def buscar_articulo(ley: str, articulo: str) -> str:
    """Texto VIGENTE de un articulo o disposicion, con su fecha de vigencia y la norma
    que le dio la redaccion actual (legislacion consolidada del BOE).

    ley: sigla (LEC, CC, CP, CE, ET, LGT, LAU, LPH, LSC, LOPDGDD, LGSS, LJCA, LPAC...),
    nombre ('Codigo Civil'), cita ('Ley 29/1998', 'LO 3/2018', 'RD 1065/2007') o BOE-A.
    Normas UE ('RGPD', 'Directiva 93/13/CEE', 'Reglamento (UE) 2024/1689') se leen de
    CELLAR en su version original publicada.
    articulo: '394', 'art. 1902', '439 bis', o una disposicion: 'DA 15ª',
    'disposicion transitoria unica'.
    """
    if es_norma_ue(ley):
        return normativa_ue.articulo_ue(ley, articulo)
    return boe.buscar_articulo(ley, articulo)


@herramienta("Buscar normas en el BOE")
def buscar_boe(consulta: str, desde: str = "", hasta: str = "", limite: int = 15) -> str:
    """Localiza leyes, reales decretos, ordenes... cuyo titulo contiene la materia, en toda
    la legislacion consolidada del BOE (mas recientes primero). Fechas AAAA-MM-DD.
    Para el texto de un articulo: buscar_articulo.
    """
    return boe.buscar_boe(consulta, desde=desde, hasta=hasta, limite=limite)


@herramienta("Sumario del BOE de un dia")
def sumario_boe(fecha: str, seccion: str = "", contiene: str = "") -> str:
    """Que se publico en el BOE un dia. fecha: AAAA-MM-DD o DD/MM/AAAA.
    contiene: filtra por texto del titulo. Devuelve los BOE-A para leer_boe.
    """
    return boe.sumario_boe(fecha, seccion=seccion, contiene=contiene)


@herramienta("Vigilar el BOE en un periodo")
def novedades_boe(contiene: str, desde: str, hasta: str, seccion: str = "") -> str:
    """Barre los sumarios del BOE entre dos fechas (max 31 dias) y devuelve lo que contiene
    el texto o NIF indicado (edictos, subvenciones, nombramientos, anuncios). AAAA-MM-DD.
    """
    return boe.novedades_boe(contiene, desde, hasta, seccion=seccion)


@herramienta("Abrir una norma del BOE")
def leer_boe(identificador: str) -> str:
    """Indice de una norma consolidada del BOE por su identificador (BOE-A-AAAA-N) y su
    enlace. Para el texto de un articulo usa buscar_articulo.
    """
    return boe.leer_boe(identificador)


@herramienta("Normativa de la UE")
def buscar_norma_ue(referencia: str, articulo: str = "") -> str:
    """Reglamento, directiva o decision de la UE en espanol.

    referencia: 'RGPD', 'Directiva 93/13/CEE', 'Reglamento (UE) 2016/679' o CELEX.
    articulo: si se indica, devuelve su texto (CELLAR, version original publicada en el
    DOUE); si no, el texto completo por tramos y el enlace al consolidado de EUR-Lex.
    """
    if articulo:
        return normativa_ue.articulo_ue(referencia, articulo)
    return normativa_ue.articulo_ue(referencia) + "\n\n" + deep_links.norma_ue(referencia)


# --------------------------------------------------------------------------
# Mercantil
# --------------------------------------------------------------------------

@herramienta("Sumario del BORME de un dia")
def sumario_borme(fecha: str, contiene: str = "") -> str:
    """Actos societarios publicados en el BORME un dia (nombramientos, constituciones,
    disoluciones, concursos). fecha AAAA-MM-DD o DD/MM/AAAA. contiene: provincia o
    denominacion social.
    """
    return mercantil.sumario_borme(fecha, contiene=contiene)


@herramienta("Ficha registral de una empresa", red=False)
def buscar_empresa_mercantil(empresa: str) -> str:
    """Prepara los buscadores oficiales del Registro Mercantil para una sociedad (nombre o
    CIF): el BORME no tiene busqueda abierta por nombre, asi que el enlace lo abres tu.
    """
    return mercantil.buscar_empresa_mercantil(empresa)


# --------------------------------------------------------------------------
# Catastro
# --------------------------------------------------------------------------

@herramienta("Consultar el Catastro")
def consultar_catastro(referencia_catastral: str = "", direccion: str = "",
                       municipio: str = "", provincia: str = "", poligono: str = "",
                       parcela: str = "", coordenadas: str = "", sigla: str = "",
                       numero: str = "") -> str:
    """Datos catastrales NO protegidos de un inmueble o finca: superficie, uso,
    antiguedad, plantas, localizacion y referencia. Por referencia_catastral, por
    direccion+municipio, por poligono+parcela+municipio o por coordenadas 'lat,lon'.
    Sin titular ni valor catastral; no cubre Pais Vasco ni Navarra.
    """
    return catastro.consultar_catastro(
        referencia_catastral=referencia_catastral, direccion=direccion,
        municipio=municipio, provincia=provincia, poligono=poligono,
        parcela=parcela, coordenadas=coordenadas, sigla=sigla, numero=numero,
    )


@herramienta("Callejero del Catastro")
def callejero_catastro(municipio: str = "", provincia: str = "", via: str = "",
                       numero: str = "") -> str:
    """Provincias, municipios o vias del Catastro, para desambiguar una direccion. Sin
    args lista provincias; con provincia, sus municipios; con via, las que coinciden.
    """
    return catastro.callejero_catastro(municipio=municipio, provincia=provincia, via=via, numero=numero)


# --------------------------------------------------------------------------
# Convenios, boletines y ordenanzas
# --------------------------------------------------------------------------

@herramienta("Localizar un convenio colectivo", red=False)
def buscar_convenio(consulta: str, territorio: str = "", ambito: str = "sector",
                    maximo: int = 8) -> str:
    """Prepara la busqueda oficial de REGCON (exige JavaScript) para un convenio por sector
    y territorio. Si ya tienes el BOE-A de su publicacion, usa leer_convenio.
    """
    return regcon.buscar_convenio(consulta, territorio=territorio, ambito=ambito, maximo=maximo)


@herramienta("Leer un convenio colectivo")
def leer_convenio(codigo: str = "", consulta: str = "", territorio: str = "",
                  articulo: str = "") -> str:
    """Texto oficial de un convenio colectivo publicado en el BOE.

    codigo: BOE-A de la publicacion (o codigo REGCON / texto libre, que redirige a la
    busqueda). articulo: solo ese articulo.
    """
    return regcon.leer_convenio(codigo=codigo, consulta=consulta, territorio=territorio, articulo=articulo)


@herramienta("Vigencia de un convenio")
def vigencia_convenio(codigo: str) -> str:
    """Estado de vigencia y tramites de un convenio (codigo REGCON de 14 digitos)."""
    return regcon.vigencia_convenio(codigo)


@herramienta("Leer un boletin autonomico o provincial")
def leer_boletin(url: str = "", boletin: str = "", ano: str = "", numero: str = "",
                 articulo: str = "", max_chars: int = 14000) -> str:
    """Texto oficial de una disposicion de un boletin AUTONOMICO o PROVINCIAL (convenios,
    ordenanzas, fiestas locales... que no estan en el BOE).

    url: URL oficial del documento (PDF o HTML), o boletin conocido ('borm') + ano +
    numero de anuncio. articulo: solo ese articulo.
    """
    return boletines.leer_boletin(url=url, boletin=boletin, ano=ano, numero=numero,
                                  articulo=articulo, max_chars=max_chars)


@herramienta("Ordenanzas municipales", red=False)
def buscar_ordenanzas(municipio: str, consulta: str = "", provincia: str = "") -> str:
    """Donde y como localizar las ordenanzas de un ayuntamiento (terrazas, ruido, residuos,
    IBI, ICIO, plusvalia, pisos turisticos, ZBE...): boletin oficial de la provincia
    (enlace verificado) y terminos de busqueda. Con la URL del anuncio, leer_boletin
    extrae el texto. provincia: necesaria si el municipio no es capital.
    """
    return ordenanzas.buscar_ordenanzas(municipio, consulta=consulta, provincia=provincia)


# --------------------------------------------------------------------------
# Calendario laboral y plazos
# --------------------------------------------------------------------------

@herramienta("Calendario laboral")
def calendario_laboral(anio: int, comunidad: str = "") -> str:
    """Fiestas laborales de un ano segun la Resolucion anual del BOE: nacionales y, con
    `comunidad` ('Murcia', 'Andalucia'), las autonomicas. NO incluye las fiestas locales.
    """
    return calendario.calendario_laboral(anio, comunidad)


@herramienta("Computo de plazos")
def computo_plazo(desde: str, dias: int, comunidad: str = "",
                  festivos_locales: str = "", naturales: bool = False) -> str:
    """Vencimiento de un plazo. `desde`: dia inicial del computo (dd/mm/aaaa), ya
    determinado (p.ej. el dia siguiente al despido). En dias habiles excluye sabados,
    domingos y festivos de la comunidad; `festivos_locales`: fechas extra separadas por
    comas. naturales=True para plazos en dias naturales.
    """
    return calendario.computo_plazo(desde, dias, comunidad=comunidad,
                                    festivos_locales=festivos_locales,
                                    naturales=naturales)


# --------------------------------------------------------------------------
# Fiscal: DGT y TEAC/TEAR
# --------------------------------------------------------------------------

@herramienta("Buscar consultas de la DGT")
def buscar_consultas_hacienda(consulta: str = "", numero: str = "", normativa: str = "",
                              desde: str = "", hasta: str = "", tipo: str = "vinculantes",
                              limite: int = 15) -> str:
    """Consultas vinculantes o generales de la Direccion General de Tributos.

    consulta: texto libre CON tildes (el buscador es sensible a acentos). numero:
    'V0282-26'. tipo: 'vinculantes' o 'generales'. Texto: leer_consulta_hacienda.
    """
    return dgt.buscar_consultas_hacienda(consulta=consulta, numero=numero, normativa=normativa,
                                         desde=desde, hasta=hasta, tipo=tipo, limite=limite)


@herramienta("Leer una consulta de la DGT")
def leer_consulta_hacienda(numero: str, max_chars: int = 30000) -> str:
    """Texto integro de una consulta de la DGT por su numero ('V0282-26')."""
    return dgt.leer_consulta_hacienda(numero, max_chars=max_chars)


@herramienta("Buscar doctrina del TEAC/TEAR")
def buscar_doctrina_teac(consulta: str = "", frase: str = "", numero_rg: str = "",
                         organo: str = "TEAC", desde: str = "", hasta: str = "",
                         maximo: int = 10) -> str:
    """Doctrina y criterios del TEAC/TEAR (via economico-administrativa).

    consulta: texto libre. frase: frase exacta (mas precisa). numero_rg: '00/06291/2024'.
    organo: 'TEAC' o un TEAR. Ficha + texto: leer_resolucion_teac.
    """
    return teac.buscar_doctrina_teac(consulta=consulta, frase=frase, numero_rg=numero_rg,
                                     organo=organo, desde=desde, hasta=hasta, maximo=maximo)


@herramienta("Leer una resolucion del TEAC/TEAR")
def leer_resolucion_teac(numero_rg: str) -> str:
    """Ficha doctrinal y enlace al texto integro de una resolucion TEA por su RG."""
    return teac.leer_resolucion_teac(numero_rg)


def _argumentos(argv: list[str] | None = None):
    import argparse

    p = argparse.ArgumentParser(
        prog="server.py",
        description="iuris-mcp. Sin argumentos: stdio (Claude Code). --http: modo remoto "
                    "streamable-http con token Bearer (IURIS_HTTP_TOKEN obligatorio).")
    p.add_argument("--http", action="store_true",
                   help="modo HTTP (tambien con IURIS_TRANSPORT=http)")
    p.add_argument("--host", help="interfaz (por defecto 127.0.0.1; IURIS_HTTP_HOST)")
    p.add_argument("--port", type=int, help="puerto (por defecto 8790; IURIS_HTTP_PORT)")
    p.add_argument("--path", help="ruta del endpoint (por defecto /mcp; IURIS_HTTP_PATH)")
    p.add_argument("--tools", help="'auditor' (por defecto), 'todas' o lista separada por "
                                   "comas (IURIS_TOOLS)")
    p.add_argument("--rpm", type=int, help="peticiones por minuto y token; 0 = sin limite "
                                           "(IURIS_HTTP_RPM, por defecto 60)")
    p.add_argument("--cendoj-uso-profesional-propio", dest="cendoj_propio", action="store_true",
                   default=None,
                   help="activa CENDOJ en remoto SOLO para uso profesional propio (su aviso legal "
                        "no permite uso comercial ni descarga masiva); equivale a "
                        "IURIS_CENDOJ_REMOTO=uso-profesional-propio")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    import os
    import sys

    args = _argumentos(argv)
    if args.http or os.environ.get("IURIS_TRANSPORT", "").strip().lower() in ("http", "streamable-http"):
        from common import remoto

        try:
            cfg = remoto.config_desde_entorno(host=args.host, port=args.port, path=args.path,
                                              tools=args.tools, rpm=args.rpm,
                                              cendoj_propio=args.cendoj_propio)
            remoto.servir(mcp, cfg)
        except remoto.ErrorConfiguracion as e:
            print(f"iuris-mcp: {e}", file=sys.stderr)
            raise SystemExit(2) from None
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
