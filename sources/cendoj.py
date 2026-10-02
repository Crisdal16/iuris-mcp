"""CENDOJ — modo 'humano en el bucle' (sin evasion de anti-bot).

CONTEXTO IMPORTANTE (decision de diseno, no una limitacion accidental):

El buscador del CENDOJ (poderjudicial.es) protege el acceso programatico con un
captcha ("Control de grandes paginaciones") que salta en la PRIMERA peticion de
un cliente HTTP no-navegador. Ademas, su aviso legal permite la consulta "para
uso particular" pero prohibe el uso comercial, la descarga masiva y la
construccion de bases de datos derivadas.

Por eso este modulo NO descarga nada del CENDOJ ni se hace pasar por un
navegador. Hace el trabajo que SI podemos hacer con rigor y valor:

  1. Normaliza la consulta (tildes, comillas, espacios).
  2. Traduce lenguaje natural -> parametros del buscador ("TSJ de Murcia" ->
     organo 33 + localizacion Murcia), usando las tablas oficiales verificadas.
  3. Construye la URL EXACTA del buscador para que la abra el USUARIO en su
     navegador, donde el es la sesion real y legitima.
  4. Analiza y verifica citas (ECLI / ROJ / Id Cendoj), que es puro parseo y no
     requiere red.

El acceso efectivo lo hace la persona. La herramienta es el copiloto.
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

from common.cendoj_ids import (
    Ecli,
    IdCendoj,
    Roj,
    normalizar_cita,
    roj_a_ecli,
)
from common.organos import (
    codigos_por_jurisdiccion,
    codigos_por_tipo_organo,
    nombre_organo,
    sigla_provincia,
)

BASE_URL = "https://www.poderjudicial.es"

# Ruta GET de la SPA del CENDOJ para busqueda por texto (la que usa el propio
# sitio en sus enlaces tematicos: /search/sentencias/<texto>/<pagina>/<base>).
_RUTA_BUSQUEDA = "/search/sentencias/{texto}/1/{base}"
# Ruta de apertura de un documento concreto (requiere el hash interno del
# CENDOJ, que solo se obtiene desde la propia lista de resultados).
_RUTA_INDICE = "/search/indexAN.jsp"


def _sin_tildes(texto: str) -> str:
    d = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in d if not unicodedata.combining(c))


def construir_busqueda(
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
    """Prepara una busqueda del CENDOJ para que la abra el usuario.

    Devuelve un dossier de texto con: la consulta normalizada, los parametros
    ya traducidos a los codigos oficiales del buscador, la URL directa para
    abrir en el navegador, y los filtros avanzados que hay que marcar a mano
    (porque el buscador avanzado va por POST y no se puede pre-rellenar por URL).
    """
    consulta = " ".join(consulta.split())
    if not consulta:
        return "Indica una consulta (texto libre) para preparar la busqueda."

    base = (base or "AN").upper()
    if base not in ("AN", "TS", "TC", "TJUE"):
        base = "AN"

    lineas: list[str] = []
    lineas.append(f"BUSQUEDA CENDOJ preparada para: «{consulta}»")
    lineas.append("")

    # --- Traduccion de filtros a codigos oficiales -------------------------
    filtros_avanzados: list[str] = []
    fuerza_an = False

    if tipo_organo:
        codigos = codigos_por_tipo_organo(tipo_organo)
        if codigos:
            nombres = ", ".join(f"{c} ({nombre_organo(c)})" for c in codigos)
            filtros_avanzados.append(f'Tipo de organo → «{tipo_organo}» = codigo(s) {nombres}')
            fuerza_an = True
        else:
            filtros_avanzados.append(
                f'Tipo de organo → «{tipo_organo}»: no reconocido; seleccionalo a mano.'
            )

    if jurisdiccion:
        jcods = codigos_por_jurisdiccion(jurisdiccion)
        etiqueta = jurisdiccion.upper()
        filtros_avanzados.append(
            f"Jurisdiccion → «{etiqueta}»" + (f" (organos {', '.join(jcods)})" if jcods else "")
        )

    if provincia:
        sig = sigla_provincia(provincia)
        if sig:
            filtros_avanzados.append(
                f'Localizacion → «{provincia}» (sigla ECLI/ROJ: {sig}). '
                f'En el desplegable "Localizacion" elige {provincia}.'
            )
            fuerza_an = True
        else:
            filtros_avanzados.append(f'Localizacion → «{provincia}»: revisa el nombre.')

    if tipo_resolucion:
        tr = tipo_resolucion.upper()
        filtros_avanzados.append(f"Tipo de resolucion → {tr} (SENTENCIA o AUTO)")

    if fecha_desde or fecha_hasta:
        filtros_avanzados.append(
            f"Fecha resolucion → desde «{fecha_desde or '...'}» hasta «{fecha_hasta or '...'}»"
        )

    if ponente:
        filtros_avanzados.append(f"Ponente → «{ponente}»")

    base_efectiva = "AN" if (fuerza_an and base == "TS") else base
    if fuerza_an and base == "TS":
        lineas.append(
            "Nota: al filtrar por provincia o tipo de organo, el CENDOJ usa la base "
            "AN (todo el CENDOJ), no solo TS. Se ajusta automaticamente."
        )
        lineas.append("")

    # --- URL directa (busqueda simple por texto) ---------------------------
    texto_url = quote(_sin_tildes(consulta), safe="")
    url = BASE_URL + _RUTA_BUSQUEDA.format(texto=texto_url, base=base_efectiva)

    lineas.append("① ABRE ESTA URL EN TU NAVEGADOR (busqueda por texto):")
    lineas.append(f"   {url}")
    lineas.append("")

    if filtros_avanzados:
        lineas.append("② AFINA CON EL BUSCADOR AVANZADO (marca estos filtros a mano):")
        for f in filtros_avanzados:
            lineas.append(f"   • {f}")
        lineas.append("")
        lineas.append(
            "   (El buscador avanzado se envia por formulario, no por URL, asi que "
            "estos filtros no pueden ir en el enlace: seleccionalos en la pagina.)"
        )
        lineas.append("")

    lineas.append(
        "③ Recientes primero: en «Ordenar» elige por fecha de resolucion descendente."
    )
    lineas.append(
        "Cuando tengas el ROJ o el ECLI de la que te interese, pasamelo a "
        "`cendoj_analizar_cita` para verificarlo, o a `leer_sentencia` para "
        "traer su texto."
    )
    lineas.append(
        "(Alternativa automatica: `buscar_sentencias` hace esta misma busqueda "
        "con un navegador y devuelve los resultados directamente.)"
    )
    return "\n".join(lineas)


def analizar_cita(cita: str) -> str:
    """Verifica y descompone una cita judicial (ECLI / ROJ / Id Cendoj).

    Puro parseo offline: no toca la red. Detecta autos (sufijo 'A'), convierte
    ROJ<->ECLI, descompone el Id Cendoj y da el enlace del buscador para que el
    usuario abra el documento en su navegador.
    """
    cita = " ".join(cita.split())
    obj = normalizar_cita(cita)
    if obj is None:
        return (
            f"No reconozco «{cita}» como ECLI, ROJ, Id Cendoj (20 digitos) ni "
            f"asunto del TJUE (C-311/19). Revisa el formato."
        )

    out: list[str] = [f"Cita analizada: «{cita}»", ""]

    ecli_para_campo = ""  # lo que se pega en el campo "ECLI" del buscador
    roj_para_campo = ""   # lo que se pega en el campo "Nº ROJ"

    if isinstance(obj, Roj):
        ecli = roj_a_ecli(obj)
        roj_para_campo = str(obj)
        if ecli:
            ecli_para_campo = str(ecli)
        out.append(f"Tipo: ROJ  ({'AUTO' if obj.es_auto else 'SENTENCIA'})")
        out.append(f"  Organo: {obj.organo}" + (f" · Provincia: {obj.provincia}" if obj.provincia else ""))
        out.append(f"  Numero/Anio: {obj.numero}/{obj.anio}")
        if ecli:
            out.append(f"  ECLI equivalente: {ecli}")
            if obj.es_auto:
                out.append("  ⚠ Es un AUTO: el ECLI termina en 'A'. Sin esa 'A' abririas la sentencia homonima.")
        else:
            out.append("  (No se puede formar el ECLI sin la sigla de provincia.)")
        texto_busqueda = str(obj)

    elif isinstance(obj, Ecli):
        ecli_para_campo = str(obj)
        out.append(f"Tipo: ECLI  ({'AUTO' if obj.es_auto else 'SENTENCIA/RESOLUCION'})")
        out.append(f"  Pais: {obj.pais} · Tribunal: {obj.tribunal} · Anio: {obj.anio} · Numero: {obj.numero}")
        if obj.es_auto:
            out.append("  ⚠ Sufijo 'A' presente: es un AUTO.")

    elif isinstance(obj, IdCendoj):
        out.append("Tipo: Id Cendoj (20 digitos)")
        out.append(f"  Municipio (INE): {obj.municipio}")
        out.append(f"  Organo: {obj.organo} → {obj.descripcion_organo}")
        out.append(f"  Seccion: {obj.seccion} · Anio: {obj.anio} · Serial: {obj.serial}")

    else:  # asunto TJUE normalizado (str)
        out.append(f"Tipo: Asunto TJUE/Tribunal General: {obj}")

    # Como abrir el documento. NO se usa la ruta /search/sentencias/<cita>/1/AN:
    # esa ruta es para BUSQUEDA POR TEXTO y el '/' del ROJ (1518/2026) rompe el
    # enrutado de la SPA. La via fiable es el buscador, pegando el ECLI/ROJ en su
    # campo dedicado.
    url_buscador = BASE_URL + _RUTA_INDICE
    out.append("")
    out.append("Para abrir el documento en tu navegador (via fiable):")
    out.append(f"  1) Abre el buscador del CENDOJ:  {url_buscador}")
    if ecli_para_campo:
        out.append(f"  2) Pega en el campo «ECLI»:  {ecli_para_campo}")
        out.append("  3) Pulsa «Buscar».")
        if roj_para_campo:
            out.append(f"  (alternativa: campo «Nº ROJ» = {roj_para_campo})")
    elif roj_para_campo:
        out.append(f"  2) Pega en el campo «Nº ROJ»:  {roj_para_campo}")
        out.append("  3) Pulsa «Buscar».")
    else:
        out.append(f"  2) Pega la cita «{cita}» en el campo correspondiente y pulsa «Buscar».")
    if ecli_para_campo or roj_para_campo:
        out.append("")
        out.append(
            "Para traer el texto sin salir de aqui: "
            f"leer_sentencia({'roj=' + repr(roj_para_campo) if roj_para_campo else 'ecli=' + repr(ecli_para_campo)})"
        )
    return "\n".join(out)
