"""Guias de redaccion de escritos juridicos.

Cada guia es un METODO (que preguntar, estructura, plazos, documentos, errores
tipicos), no una plantilla para rellenar. Los plazos y requisitos citados se
contrastaron con la redaccion VIGENTE del BOE el 2026-10-02 (tras la LO 1/2025
y el RDL 6/2023), y cada guia lleva la lista de articulos que la sustentan:
con `verificar=True` la tool los descarga en el momento del BOE, para que
ningun plazo dependa de lo que se escribio aqui.

Lo que la guia NO hace: no fija la estrategia ni sustituye el criterio del
abogado; donde hay doctrina discutida se dice y se remite a buscar_sentencias.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from common.texto import norm

# Comun a todo el orden civil desde el 03/04/2025.
_MASC = (
    "MASC (LO 1/2025, art. 5): en el orden civil es requisito de procedibilidad haber "
    "acudido antes a un medio adecuado de solucion de controversias (negociacion directa "
    "o entre abogados, mediacion, conciliacion, oferta vinculante confidencial, opinion "
    "de experto...) con identidad de objeto. Hay que DESCRIBIR ese intento en la demanda "
    "(art. 399.3 LEC) y aportar el documento que lo acredita (art. 264.4º LEC); si falta, "
    "la demanda se inadmite (art. 403.2 LEC). Excepciones tasadas en el art. 5.2-3 LO "
    "1/2025 (derechos fundamentales, art. 158 CC, apoyo a la discapacidad, filiacion, "
    "tutela sumaria de la posesion, obra ruinosa, menores, juicio cambiario, ejecucion, "
    "cautelares previas, diligencias preliminares...). La solicitud de negociacion "
    "interrumpe la prescripcion / suspende la caducidad (art. 7)."
)

GUIAS: dict[str, dict] = {
    # ------------------------------------------------------------------ CIVIL
    "demanda-juicio-verbal": {
        "jurisdiccion": "civil",
        "titulo": "Demanda de juicio verbal",
        "cuando": "Cuantia hasta 15.000 EUR (art. 250.2 LEC) o materias del art. 250.1 LEC "
                  "cualquiera que sea la cuantia (desahucios y rentas, precario, tutela "
                  "sumaria de la posesion, propiedad horizontal en ciertos casos...).",
        "preguntas": [
            "Cuantia exacta y como se calcula (arts. 251-253 LEC).",
            "Que MASC se intento, cuando, con que objeto y con que resultado (documento).",
            "Domicilio del demandado y medios electronicos de contacto.",
            "Prueba disponible: documentos, testigos, pericial (se aporta con la demanda).",
            "Si la cuantia no supera 2.000 EUR: va sin abogado ni procurador (arts. 23 y 31 LEC)?",
        ],
        "estructura": [
            "Encabezamiento: al Tribunal de Instancia (Seccion Civil) competente; datos del "
            "actor con telefono y correo (art. 399.1 LEC); procurador y abogado.",
            "Hechos numerados y separados; documento que acredita cada uno.",
            "Descripcion del proceso de negociacion previo (MASC) o su imposibilidad.",
            "Fundamentos de derecho procesales (jurisdiccion, competencia, legitimacion, "
            "procedimiento y cuantia) y de fondo.",
            "Suplico con pronunciamientos separados; intereses; costas.",
            "Otrosies: prueba (si se pide vista), medios de notificacion.",
        ],
        "plazos": "El demandado contesta por escrito en DIEZ dias (art. 438.1 LEC). Desde la "
                  "reforma la demanda verbal tiene el contenido y forma del ordinario "
                  "(art. 437.1 LEC), salvo la sucinta sin abogado (art. 437.2).",
        "errores": [
            "Olvidar el MASC o no describirlo: inadmision (art. 403.2 LEC).",
            "Contar con apelar: no son apelables las sentencias de verbales por cuantia "
            "que no supere 3.000 EUR (art. 455.1 LEC).",
            "Aplicar el umbral antiguo de 6.000 EUR (hoy 15.000).",
        ],
        "verificar": [("LEC", "250"), ("LEC", "437"), ("LEC", "438"), ("LEC", "399"),
                      ("LEC", "264"), ("LEC", "403"), ("LEC", "455"), ("LO 1/2025", "5")],
    },
    "demanda-juicio-ordinario": {
        "jurisdiccion": "civil",
        "titulo": "Demanda de juicio ordinario",
        "cuando": "Cuantia superior a 15.000 EUR o indeterminada, y materias del art. 249.1 "
                  "LEC (honor e intimidad y demas derechos fundamentales, impugnacion de "
                  "acuerdos sociales, competencia desleal, propiedad industrial e "
                  "intelectual, arrendamientos salvo rentas o desahucio...).",
        "preguntas": [
            "Accion o acciones y su acumulacion; legitimacion activa y pasiva.",
            "Cuantia (arts. 251-253 LEC) y competencia territorial.",
            "MASC: tipo, fechas, objeto, acreditacion.",
            "Plazo de prescripcion o caducidad y si el MASC lo interrumpio (art. 7 LO 1/2025).",
            "Documentos y dictamenes: deben ir con la demanda (arts. 265 y 336 LEC).",
        ],
        "estructura": [
            "Encabezamiento con datos de identificacion y de contacto electronico (art. 399.1).",
            "Hechos numerados, con documento de apoyo en cada uno (art. 399.3).",
            "Descripcion del MASC previo (art. 399.3, parrafo segundo).",
            "Fundamentos: procesales separados de los de fondo (art. 399.4).",
            "Suplico con pronunciamientos separados (art. 399.5).",
            "Otrosies: documentos, prueba anticipada, medidas cautelares si procede.",
        ],
        "plazos": "Contestacion en VEINTE dias desde el emplazamiento (art. 404.1 LEC).",
        "errores": [
            "No aportar con la demanda los documentos de fondo: precluye (art. 269 LEC).",
            "Mezclar en un mismo hecho varios hechos: dificulta la admision/negacion.",
            "No acreditar el MASC o hacerlo sin identidad de objeto.",
        ],
        "verificar": [("LEC", "249"), ("LEC", "399"), ("LEC", "264"), ("LEC", "265"),
                      ("LEC", "403"), ("LEC", "404"), ("LO 1/2025", "5"), ("LO 1/2025", "7")],
    },
    "contestacion-demanda-civil": {
        "jurisdiccion": "civil",
        "titulo": "Contestacion a la demanda (civil)",
        "cuando": "Tras el emplazamiento en un ordinario (20 dias, art. 404 LEC) o en un "
                  "verbal (10 dias, art. 438.1 LEC).",
        "preguntas": [
            "Fecha de notificacion del emplazamiento (computo del plazo).",
            "Excepciones procesales: falta de jurisdiccion/competencia (declinatoria en "
            "los primeros dias del plazo, art. 64 LEC), falta de MASC, litispendencia...",
            "Hechos que se admiten y cuales se niegan, uno a uno.",
            "Reconvencion o credito compensable.",
        ],
        "estructura": [
            "Encabezamiento y personacion.",
            "Hechos: correlativos a los de la demanda, admitiendo o negando cada uno "
            "(el silencio o la evasiva puede tomarse como admision, art. 405.2 LEC).",
            "Excepciones procesales (art. 405.3) y materiales (art. 405.1).",
            "Fundamentos de derecho.",
            "Suplico: absolucion / desestimacion, costas; reconvencion con su propio suplico.",
        ],
        "plazos": "Ordinario: 20 dias (art. 404.1). Verbal: 10 dias, y la reconvencion se "
                  "contesta tambien en 10 (art. 438.1-2).",
        "errores": [
            "Respuestas evasivas a los hechos (art. 405.2).",
            "Plantear la declinatoria fuera de plazo.",
            "Reconvenir en un verbal que acaba sin cosa juzgada (art. 438.2).",
        ],
        "verificar": [("LEC", "404"), ("LEC", "405"), ("LEC", "438"), ("LEC", "64")],
    },
    "peticion-monitorio": {
        "jurisdiccion": "civil",
        "titulo": "Peticion inicial de proceso monitorio",
        "cuando": "Deuda dineraria de CUALQUIER importe, liquida, determinada, vencida y "
                  "exigible, acreditada documentalmente (art. 812 LEC).",
        "preguntas": [
            "Documento que acredita la deuda (firmado por el deudor, facturas, albaranes, "
            "certificacion de la comunidad de propietarios...).",
            "Si el deudor es consumidor: el juez controla de oficio las clausulas abusivas "
            "antes del requerimiento y puede proponer un importe menor, que el acreedor "
            "acepta o rechaza en diez dias (art. 815.3 LEC) — revisar intereses y "
            "penalizaciones antes de pedir.",
            "MASC: el monitorio esta en el libro IV LEC y no figura entre las excepciones "
            "del art. 5.2 LO 1/2025; hay discusion practica — comprobar el criterio del "
            "partido judicial y, en la duda, acreditarlo.",
        ],
        "estructura": [
            "Puede usarse el impreso normalizado; sin abogado ni procurador en la peticion "
            "inicial (arts. 23.2.1º y 31.2.1º LEC).",
            "Identificacion de deudor y acreedor, domicilio, origen y cuantia de la deuda.",
            "Documentos que la acreditan.",
        ],
        "plazos": "Requerimiento al deudor para pagar u oponerse en VEINTE dias "
                  "(art. 815.1 LEC). Si se opone y la cuantia excede del verbal, el "
                  "acreedor tiene UN MES para presentar demanda de ordinario (art. 818.2).",
        "errores": [
            "Incluir conceptos no liquidos o no vencidos.",
            "No presentar la demanda de ordinario en el mes tras la oposicion: "
            "sobreseimiento y costas (art. 818.2).",
        ],
        "verificar": [("LEC", "812"), ("LEC", "815"), ("LEC", "818"), ("LEC", "23"),
                      ("LEC", "31"), ("LO 1/2025", "5")],
    },
    "oposicion-monitorio": {
        "jurisdiccion": "civil",
        "titulo": "Escrito de oposicion al monitorio",
        "cuando": "Tras el requerimiento de pago del art. 815 LEC.",
        "preguntas": [
            "Fecha del requerimiento (plazo de 20 dias).",
            "Motivos: inexistencia de la deuda, pago, pluspeticion, clausulas abusivas...",
            "Cuantia: si requiere abogado y procurador (art. 818.1 LEC).",
        ],
        "estructura": [
            "Oposicion FUNDADA Y MOTIVADA (art. 815.1 LEC, redaccion vigente): no basta "
            "con negar la deuda.",
            "Si se alega pluspeticion, cuantificar lo reconocido (art. 818.1 y 21.2 LEC).",
            "Suplico: que se tenga por formulada la oposicion y se siga el juicio que "
            "corresponda.",
        ],
        "plazos": "VEINTE dias desde el requerimiento (art. 815.1 LEC).",
        "errores": [
            "Oposicion generica sin fundamentar.",
            "Firmarla sin abogado/procurador cuando por cuantia son preceptivos.",
        ],
        "verificar": [("LEC", "815"), ("LEC", "818"), ("LEC", "21")],
    },
    "recurso-apelacion-civil": {
        "jurisdiccion": "civil",
        "titulo": "Recurso de apelacion (civil)",
        "cuando": "Contra sentencias y autos definitivos (art. 455.1 LEC), salvo sentencias "
                  "de verbales por cuantia que no supere 3.000 EUR.",
        "preguntas": [
            "Fecha de notificacion de la resolucion (plazo de 20 dias).",
            "Pronunciamientos concretos que se impugnan.",
            "Infracciones: procesales (con protesta en su momento) y de fondo; error en "
            "la valoracion de la prueba (con cita de la grabacion).",
            "Prueba en segunda instancia: solo en los casos del art. 460 LEC.",
            "Deposito para recurrir (DA 15ª LOPJ) y su justificante.",
        ],
        "estructura": [
            "Escrito de INTERPOSICION ante el tribunal competente para conocer del recurso "
            "(art. 458.1 LEC, redaccion del RDL 6/2023), con copia de la resolucion.",
            "Cita de la resolucion apelada y de los pronunciamientos impugnados (art. 458.2).",
            "Alegaciones ordenadas por motivo; suplico de revocacion y nueva resolucion.",
        ],
        "plazos": "VEINTE dias desde la notificacion (art. 458.1). La parte apelada se opone "
                  "o impugna en DIEZ dias (art. 461.1).",
        "errores": [
            "Presentarlo ante el juzgado de origen por inercia del regimen anterior.",
            "Apelar una sentencia de verbal por cuantia <= 3.000 EUR (art. 455.1).",
            "Reproducir la demanda sin criticar la sentencia.",
            "Olvidar el deposito.",
        ],
        "verificar": [("LEC", "455"), ("LEC", "458"), ("LEC", "460"), ("LEC", "461"),
                      ("LOPJ", "DA 15ª")],
    },
    "recurso-reposicion-civil": {
        "jurisdiccion": "civil",
        "titulo": "Recurso de reposicion (civil)",
        "cuando": "Contra providencias y autos no definitivos, ante el mismo tribunal "
                  "(art. 451 LEC); para decretos y diligencias del LAJ, ver arts. 451-454 bis.",
        "preguntas": ["Fecha de notificacion.", "Infraccion concreta que comete la resolucion."],
        "estructura": [
            "Identificacion de la resolucion recurrida.",
            "Expresion de la infraccion en que incurre (requisito de admision, art. 452).",
            "Suplico de reposicion y nueva resolucion.",
        ],
        "plazos": "CINCO dias (art. 452 LEC). No suspende lo acordado (art. 451).",
        "errores": ["No expresar la infraccion: inadmision sin recurso (art. 452)."],
        "verificar": [("LEC", "451"), ("LEC", "452")],
    },
    # ---------------------------------------------------------------- LABORAL
    "demanda-despido": {
        "jurisdiccion": "laboral",
        "titulo": "Papeleta de conciliacion y demanda por despido",
        "cuando": "Despido disciplinario u objetivo, o extincion que se impugna como despido.",
        "preguntas": [
            "Fecha de efectos del despido (inicio de la caducidad).",
            "Carta de despido y causa alegada; antiguedad, salario, categoria, convenio.",
            "Representacion legal o afiliacion sindical (garantias).",
            "Posible nulidad: vulneracion de derechos fundamentales, embarazo, "
            "conciliacion... (cambia la modalidad y el contenido).",
        ],
        "estructura": [
            "1) Papeleta de conciliacion ante el servicio administrativo (art. 63 LRJS): "
            "los hechos que no se aleguen aqui no podran alegarse luego (art. 80.1.c LRJS).",
            "2) Demanda (art. 80 LRJS): organo y modalidad procesal; partes; hechos "
            "(incluidos los datos del art. 104 LRJS); acto de conciliacion intentado; "
            "suplica de improcedencia o nulidad con sus consecuencias.",
        ],
        "plazos": "VEINTE dias HABILES de caducidad desde el despido; no cuentan sabados, "
                  "domingos ni festivos en la sede del juzgado (art. 103.1 LRJS; art. 59.3 "
                  "ET). La papeleta suspende/interrumpe el computo (art. 59.3 ET y art. 65 "
                  "LRJS). Usa computo_plazo con festivos locales.",
        "errores": [
            "Computar dias naturales o incluir sabados.",
            "Hechos nuevos en la demanda no recogidos en la papeleta.",
            "Demandar a quien no es el empresario real (art. 103.2 LRJS).",
        ],
        "verificar": [("LRJS", "63"), ("LRJS", "64"), ("LRJS", "65"), ("LRJS", "80"),
                      ("LRJS", "103"), ("LRJS", "104"), ("ET", "59")],
    },
    # ------------------------------------------------------------ CONTENCIOSO
    "recurso-contencioso": {
        "jurisdiccion": "contencioso",
        "titulo": "Escrito de interposicion de recurso contencioso-administrativo",
        "cuando": "Contra actos que ponen fin a la via administrativa, disposiciones, "
                  "inactividad o via de hecho.",
        "preguntas": [
            "Acto impugnado, fecha de notificacion y si agota la via administrativa.",
            "Si hubo recurso de reposicion potestativo y cuando se resolvio.",
            "Organo competente (Juzgado o Sala) segun arts. 8-12 LJCA.",
            "Procedimiento: ordinario o abreviado (art. 78 LJCA).",
        ],
        "estructura": [
            "Escrito REDUCIDO: citar el acto o disposicion y pedir que se tenga por "
            "interpuesto (art. 45.1 LJCA), salvo abreviado o lesividad.",
            "Documentos: representacion, legitimacion, copia del acto, acuerdo para "
            "litigar de la persona juridica (art. 45.2 LJCA).",
            "La demanda se formaliza despues, con el expediente (art. 52 y ss.).",
        ],
        "plazos": "DOS meses desde el dia siguiente a la notificacion del acto expreso; "
                  "si no es expreso, la regla del art. 46.1 LJCA (seis meses), con la "
                  "doctrina constitucional y del TS sobre el silencio negativo — "
                  "comprobarla con buscar_tc / buscar_sentencias antes de confiar en ese "
                  "plazo. Agosto es inhabil para interponer (art. 128.2 LJCA).",
        "errores": [
            "Olvidar el acuerdo del organo de la persona juridica (art. 45.2.d): causa "
            "frecuente de inadmision.",
            "Contar el plazo desde la notificacion del acto cuando hubo reposicion "
            "(art. 46.4).",
        ],
        "verificar": [("LJCA", "45"), ("LJCA", "46"), ("LJCA", "69"), ("LJCA", "128")],
    },
    "recurso-administrativo": {
        "jurisdiccion": "contencioso",
        "titulo": "Recurso de alzada o de reposicion (via administrativa)",
        "cuando": "Alzada: actos que NO ponen fin a la via administrativa (art. 121 LPAC). "
                  "Reposicion potestativa: actos que la agotan (art. 123 LPAC).",
        "preguntas": ["Acto, organo que lo dicto y si agota la via.", "Fecha de notificacion."],
        "estructura": [
            "Identificacion del recurrente y del acto; organo al que se dirige.",
            "Alegaciones (motivos de nulidad o anulabilidad, arts. 47-48 LPAC).",
            "Solicitud; si procede, suspension de la ejecucion (art. 117 LPAC).",
        ],
        "plazos": "UN mes si el acto es expreso, en ambos recursos (arts. 122.1 y 124.1 LPAC); "
                  "contra actos presuntos, en cualquier momento. Resolucion: alzada 3 meses, "
                  "reposicion 1 mes.",
        "errores": [
            "Interponer reposicion contra un acto que no agota la via (procede alzada).",
            "Dejar firme el acto por pasar el mes de la alzada.",
        ],
        "verificar": [("LPAC", "112"), ("LPAC", "121"), ("LPAC", "122"), ("LPAC", "123"),
                      ("LPAC", "124")],
    },
    # ------------------------------------------------------------------ PENAL
    "querella": {
        "jurisdiccion": "penal",
        "titulo": "Querella criminal",
        "cuando": "Para ejercitar la accion penal como acusacion particular o popular.",
        "preguntas": [
            "Hechos con lugar, fecha y hora; autor conocido o señas que lo identifiquen.",
            "Delito y juzgado competente (lugar de comision).",
            "Poder especial del procurador o firma del querellante (art. 277.7º LECrim).",
            "Fianza si es accion popular.",
        ],
        "estructura": [
            "Requisitos del art. 277 LECrim: juez, querellante, querellado, relacion "
            "circunstanciada del hecho, diligencias que se piden, peticion de admision y "
            "medidas, firma.",
            "Calificacion juridica provisional y prescripcion del delito.",
        ],
        "plazos": "No hay plazo procesal; el limite es la prescripcion del delito (arts. "
                  "131-132 CP).",
        "errores": [
            "Relato generico sin circunstancias de tiempo y lugar.",
            "Procurador sin poder especial.",
        ],
        "verificar": [("LECRIM", "277"), ("CP", "131"), ("CP", "132")],
    },
}


def _buscar(escrito: str, jurisdiccion: str) -> list[str]:
    q = norm(escrito).replace("-", " ")
    j = norm(jurisdiccion)
    cands = []
    for gid, g in GUIAS.items():
        if j and norm(g["jurisdiccion"]) != j:
            continue
        texto = norm(gid.replace("-", " ") + " " + g["titulo"])
        if q and norm(gid) == norm(escrito):
            return [gid]
        palabras = [p for p in q.split() if len(p) > 3]
        if not palabras or all(p in texto for p in palabras):
            cands.append(gid)
    return cands


def catalogo(jurisdiccion: str = "") -> str:
    j = norm(jurisdiccion)
    out = ["Guias de escritos disponibles (id — titulo):", ""]
    actual = None
    for gid, g in sorted(GUIAS.items(), key=lambda kv: kv[1]["jurisdiccion"]):
        if j and norm(g["jurisdiccion"]) != j:
            continue
        if g["jurisdiccion"] != actual:
            actual = g["jurisdiccion"]
            out.append(f"[{actual.upper()}]")
        out.append(f"  • {gid} — {g['titulo']}")
    out.append("\nAbre una con guia_escrito('<id>'). Para el resto de escritos: estructura "
               "general (encabezamiento, hechos, fundamentos, suplico) + buscar_articulo de "
               "la norma procesal aplicable.")
    return "\n".join(out)


def _verificar(arts: list[tuple[str, str]]) -> list[str]:
    from sources import boe

    def uno(a: tuple[str, str]) -> str:
        try:
            r = boe.buscar_articulo(*a)
        except Exception as e:  # noqa: BLE001
            return f"  · {a[0]} art. {a[1]}: no se pudo comprobar ({type(e).__name__})"
        futura = re.search(r"AVISO: hay una redaccion FUTURA[^\n]*", r)
        cuerpo = r.split("Notas del BOE")[0]
        cab, _, resto = cuerpo.partition("\n\n")
        resto = " ".join(resto.split())
        linea = f"  · {cab}\n    {resto[:420]}{'…' if len(resto) > 420 else ''}"
        if futura:
            linea += f"\n    ⚠ {futura.group(0)}"
        return linea

    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(uno, arts))


def guia_escrito(escrito: str = "", jurisdiccion: str = "", verificar: bool = True) -> str:
    if not escrito.strip():
        return catalogo(jurisdiccion)
    cands = _buscar(escrito, jurisdiccion)
    if not cands:
        return (f"No tengo guia para «{escrito}»" + (f" en {jurisdiccion}" if jurisdiccion else "")
                + ".\n\n" + catalogo(jurisdiccion))
    if len(cands) > 1:
        return ("Hay varias guias posibles; elige una:\n" +
                "\n".join(f"  • {c} — {GUIAS[c]['titulo']}" for c in cands))
    gid = cands[0]
    g = GUIAS[gid]
    out = [f"GUIA: {g['titulo']}  [{gid} · {g['jurisdiccion']}]", "",
           f"Cuando: {g['cuando']}", ""]
    if g["jurisdiccion"] == "civil":
        out += [_MASC, ""]
    out += ["Preguntas al abogado antes de redactar:"] + [f"  - {p}" for p in g["preguntas"]]
    out += ["", "Estructura:"] + [f"  {i}. {e}" for i, e in enumerate(g["estructura"], 1)]
    out += ["", f"Plazos: {g['plazos']}", "", "Errores tipicos:"] + [f"  - {e}" for e in g["errores"]]
    if verificar:
        out += ["", "Base legal VIGENTE comprobada ahora en el BOE (extracto):"]
        out += _verificar(g["verificar"])
    else:
        out += ["", "Base legal (compruebala con buscar_articulo): " +
                ", ".join(f"{n} {a}" for n, a in g["verificar"])]
    out += ["", "Metodo: redacta con estos datos; cita la jurisprudencia con buscar_sentencias "
            "+ leer_sentencia (parrafo literal) y, al final, pasa el borrador por "
            "verificar_escrito. Fechas de vencimiento: computo_plazo."]
    return "\n".join(out)
