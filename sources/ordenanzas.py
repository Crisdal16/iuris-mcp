"""Ordenanzas municipales (humano en el bucle + lectura automatica).

No hay una fuente unica: cada ayuntamiento publica sus ordenanzas en el Boletin
Oficial de su PROVINCIA (o de su CCAA uniprovincial) y, a veces, en un catalogo
de su sede electronica. Cada boletin tiene un buscador distinto (muchos con
formularios JS o anti-bot), asi que esta tool NO rastrea: prepara la busqueda
oficial (boletin + terminos) para que la abras y, en cuanto tengas la URL del
anuncio o del PDF, `leer_boletin(url=...)` extrae el texto (o un articulo).

Las URLs de los boletines se comprobaron una a una (HTTP 200) el 2026-10-02.
Las que no respondieron se dejan sin URL y se indica como localizarlas, en
lugar de inventarlas.
"""

from __future__ import annotations

from common.texto import norm

# provincia (normalizada) -> (nombre del boletin, URL verificada o "")
BOP: dict[str, tuple[str, str]] = {
    "A CORUNA": ("BOP da Coruña", "https://bop.dacoruna.gal/bopportal/"),
    "ALAVA": ("BOTHA (Álava)", "https://www.araba.eus/botha/Inicio/SGBO5001.aspx?Idi=es"),
    "ALBACETE": ("BOP de Albacete", "https://www.dipualba.es/bop/"),
    "ALICANTE": ("BOP de Alicante", ""),
    "ALMERIA": ("BOP de Almería", ""),
    "ASTURIAS": ("BOPA (Asturias)", "https://miprincipado.asturias.es/bopa"),
    "AVILA": ("BOP de Ávila", ""),
    "BADAJOZ": ("BOP de Badajoz", "https://www.dip-badajoz.es/bop/"),
    "BARCELONA": ("BOP de Barcelona", "https://bop.diba.cat/"),
    "BIZKAIA": ("BOB (Bizkaia)", "https://www.bizkaia.eus/es/bob"),
    "BURGOS": ("BOP de Burgos", ""),
    "CACERES": ("BOP de Cáceres", "https://bop.dip-caceres.es/bop/index.html"),
    "CADIZ": ("BOP de Cádiz", "https://www.bopcadiz.es/"),
    "CANTABRIA": ("BOC (Cantabria)", "https://boc.cantabria.es/boces/"),
    "CASTELLON": ("BOP de Castellón", "https://bop.dipcas.es/PortalBOP/"),
    "CEUTA": ("BOCCE (Ceuta)", "https://www.ceuta.es/ceuta/bocce"),
    "CIUDAD REAL": ("BOP de Ciudad Real", "https://bop.dipucr.es/"),
    "CORDOBA": ("BOP de Córdoba", "https://bop.dipucordoba.es/"),
    "CUENCA": ("BOP de Cuenca", ""),
    "GIPUZKOA": ("BOG (Gipuzkoa)", "https://egoitza.gipuzkoa.eus/es/bog"),
    "GIRONA": ("BOP de Girona", "https://www.ddgi.cat/bop/"),
    "GRANADA": ("BOP de Granada", "https://bop.dipgra.es/publica/consulta-de-bops/"),
    "GUADALAJARA": ("BOP de Guadalajara", "https://boletin.dguadalajara.es/"),
    "HUELVA": ("BOP de Huelva", ""),
    "HUESCA": ("BOP de Huesca", "https://bop.dphuesca.es/publica/consulta-de-bops/"),
    "ILLES BALEARS": ("BOIB (Illes Balears)", "https://www.caib.es/eboibfront/"),
    "JAEN": ("BOP de Jaén", "https://bop.dipujaen.es/"),
    "LA RIOJA": ("BOR (La Rioja)", "https://web.larioja.org/bor-portada"),
    "LAS PALMAS": ("BOP de Las Palmas", "https://www.boplaspalmas.net/"),
    "LEON": ("BOP de León", "https://bop.dipuleon.es/"),
    "LLEIDA": ("BOP de Lleida", "https://bop.diputaciolleida.cat/"),
    "LUGO": ("BOP de Lugo", ""),
    "MADRID": ("BOCM (Comunidad de Madrid)", "https://www.bocm.es/"),
    "MALAGA": ("BOP de Málaga", "https://www.bopmalaga.es/"),
    "MELILLA": ("BOME (Melilla)", ""),
    "MURCIA": ("BORM (Región de Murcia)", "https://www.borm.es/"),
    "NAVARRA": ("BON (Navarra)", "https://bon.navarra.es/es/inicio"),
    "OURENSE": ("BOP de Ourense", "https://bop.depourense.es/portal/"),
    "PALENCIA": ("BOP de Palencia", ""),
    "PONTEVEDRA": ("BOP de Pontevedra", "https://boppo.depo.gal/"),
    "SALAMANCA": ("BOP de Salamanca", ""),
    "SANTA CRUZ DE TENERIFE": ("BOP de Santa Cruz de Tenerife", "https://www.bopsantacruzdetenerife.es/"),
    "SEGOVIA": ("BOP de Segovia", "https://www.dipsegovia.es/bop"),
    "SEVILLA": ("BOP de Sevilla", "https://www.dipusevilla.es/bop/"),
    "SORIA": ("BOP de Soria", "https://bop.dipsoria.es/"),
    "TARRAGONA": ("BOP de Tarragona", ""),
    "TERUEL": ("BOP de Teruel", "https://236ws.dpteruel.es/DPT/bopt.nsf"),
    "TOLEDO": ("BOP de Toledo", "https://bop.diputoledo.es/"),
    "VALENCIA": ("BOP de Valencia", "https://bop.dival.es/bop/"),
    "VALLADOLID": ("BOP de Valladolid", "https://bop.sede.diputaciondevalladolid.es/"),
    "ZAMORA": ("BOP de Zamora", ""),
    "ZARAGOZA": ("BOP de Zaragoza", "https://bop.dpz.es/BOPZ/"),
}

_ALIAS = {
    "LA CORUNA": "A CORUNA", "CORUNA": "A CORUNA", "ARABA": "ALAVA", "VITORIA": "ALAVA",
    "ALACANT": "ALICANTE", "VIZCAYA": "BIZKAIA", "BILBAO": "BIZKAIA", "GUIPUZCOA": "GIPUZKOA",
    "SAN SEBASTIAN": "GIPUZKOA", "DONOSTIA": "GIPUZKOA", "BALEARES": "ILLES BALEARS",
    "PALMA": "ILLES BALEARS", "MALLORCA": "ILLES BALEARS", "GERONA": "GIRONA",
    "LERIDA": "LLEIDA", "ORENSE": "OURENSE", "CASTELLO": "CASTELLON", "OVIEDO": "ASTURIAS",
    "LOGRONO": "LA RIOJA", "SANTANDER": "CANTABRIA", "PAMPLONA": "NAVARRA",
    "TENERIFE": "SANTA CRUZ DE TENERIFE", "GRAN CANARIA": "LAS PALMAS",
    "LAS PALMAS DE GRAN CANARIA": "LAS PALMAS", "VALENCIA/VALENCIA": "VALENCIA",
}

# Materias frecuentes -> terminos que suelen aparecer en el titulo de la ordenanza
_MATERIAS = {
    "TERRAZA": "ordenanza terrazas veladores via publica",
    "RUIDO": "ordenanza ruidos vibraciones contaminacion acustica",
    "RESIDUO": "ordenanza limpieza residuos",
    "BASURA": "ordenanza limpieza residuos tasa basura",
    "ANIMAL": "ordenanza tenencia animales compania",
    "TURISTIC": "viviendas uso turistico modificacion plan general",
    "IBI": "ordenanza fiscal impuesto bienes inmuebles",
    "ICIO": "ordenanza fiscal impuesto construcciones instalaciones obras",
    "PLUSVALIA": "ordenanza fiscal incremento valor terrenos naturaleza urbana",
    "IAE": "ordenanza fiscal impuesto actividades economicas",
    "IVTM": "ordenanza fiscal vehiculos traccion mecanica",
    "ZBE": "ordenanza movilidad zona bajas emisiones",
    "MOVILIDAD": "ordenanza movilidad circulacion",
    "VENTA AMBULANTE": "ordenanza venta ambulante mercadillo",
    "OBRA": "ordenanza licencias urbanisticas declaracion responsable obras",
}


def _provincia(provincia: str, municipio: str) -> str | None:
    for cand in (provincia, municipio):
        n = norm(cand or "")
        if not n:
            continue
        n = _ALIAS.get(n, n)
        if n in BOP:
            return n
    return None


def _terminos(consulta: str) -> str:
    n = norm(consulta)
    for clave, terminos in _MATERIAS.items():
        if clave in n:
            return terminos
    return f"ordenanza {consulta}".strip()


def buscar_ordenanzas(municipio: str, consulta: str = "", provincia: str = "") -> str:
    municipio = " ".join((municipio or "").split())
    if not municipio:
        return "Indica el municipio (y, si no es capital de provincia, la provincia)."
    prov = _provincia(provincia, municipio)
    terminos = _terminos(consulta) if consulta else "ordenanza"
    lineas = [f"Ordenanzas de {municipio}" + (f" sobre «{consulta}»" if consulta else ""), ""]

    if prov is None:
        lineas += [
            f"No se en que provincia esta «{municipio}». Repite con `provincia` "
            "(p.ej. provincia='Murcia').",
            f"Mientras tanto: sede electronica del Ayuntamiento de {municipio} → "
            "Normativa / Ordenanzas (suele tener el texto consolidado).",
        ]
        return "\n".join(lineas)

    nombre, url = BOP[prov]
    lineas.append("Donde se publican (texto oficial con fuerza de obligar):")
    if url:
        lineas.append(f"  • {nombre}: {url}")
    else:
        lineas.append(f"  • {nombre}: web de la Diputacion/CCAA (no verificada automaticamente; "
                      "busca «Boletín Oficial de la Provincia» en la web de la Diputación).")
    lineas += [
        f"    Busca en el boletin: «{municipio}» + «{terminos}». Las ordenanzas fiscales "
        "se modifican casi cada año: localiza la ULTIMA modificacion (aprobacion definitiva).",
        f"  • Sede electronica del Ayuntamiento de {municipio} → Normativa / Ordenanzas "
        "(texto consolidado, sin valor oficial pero comodo para orientarse).",
        "",
        "Cuando tengas la URL del anuncio o del PDF: leer_boletin(url='<url>') devuelve el "
        "texto (o leer_boletin(url=..., articulo='N') un articulo). Ojo con la aprobacion "
        "inicial vs. definitiva: solo la definitiva, publicada integra, entra en vigor "
        "(art. 70.2 LBRL — compruebalo con buscar_articulo('LBRL', '70')).",
    ]
    return "\n".join(lineas)
