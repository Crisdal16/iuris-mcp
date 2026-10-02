---
name: investigacion-juridica
description: Método para investigar una cuestión de Derecho español (y de la UE aplicable en España) con fuentes OFICIALES a través del MCP iuris — norma vigente, jurisprudencia del TS/TSJ/AP, Tribunal Constitucional y TJUE, doctrina de la DGT/TEAC, verificación de cada cita — y entregar una nota de investigación lista para el expediente. Úsala siempre que el usuario plantee un caso o una pregunta jurídica que requiera fundamentarse ("¿puede mi cliente...?", "¿qué plazo hay para...?", "¿qué dice el Supremo sobre...?", "prepárame una nota sobre...", "argumentos para recurrir..."), cuando pida doctrina o jurisprudencia sobre un tema, o cuando vaya a redactar un escrito y necesite primero la base legal, aunque no diga "investigar". No la uses para preguntas de cultura general sobre el Derecho que no requieren fuentes, ni para Derecho extranjero.
---

# Investigación jurídica con fuentes oficiales

El valor de una nota jurídica está en que cada afirmación se pueda rastrear hasta
una fuente oficial **vigente**. Un modelo que responde de memoria mezcla
redacciones derogadas, inventa números de sentencia y confunde plazos; por eso aquí
todo se apoya en el MCP **iuris** y nada se cita sin haberlo leído en esa sesión.

## 1. Delimitar la cuestión (antes de buscar)

Reformula la consulta en una o varias preguntas jurídicas concretas y anota:
- orden jurisdiccional y rama (civil, laboral, contencioso, penal, tributario);
- hechos relevantes y fechas (la norma aplicable puede depender de la fecha de los
  hechos, no de hoy);
- territorio (Derecho foral, CCAA, municipio);
- qué necesita el usuario: una respuesta, un plazo, argumentos, o un escrito.

Si falta un dato que cambia la respuesta (p. ej. fecha del despido, cuantía), dilo y
pregúntalo, o investiga las alternativas por separado.

## 2. Norma vigente

- Localiza la norma: `buscar_boe('<materia>')` si no sabes cuál es.
- Lee cada precepto con `buscar_articulo(ley, articulo)`. Fíjate en «vigente desde»,
  en «redaccion vigente dada por» y en el AVISO de redacción futura: una reforma
  reciente (p. ej. la LO 1/2025 en la LEC) cambia plazos y requisitos.
- Si los hechos son anteriores a la última reforma, dilo expresamente y valora el
  régimen transitorio (disposiciones transitorias: `buscar_articulo(ley, 'DT 1ª')`).
- Derecho UE: `buscar_articulo('RGPD', '17')` / `buscar_norma_ue`. CELLAR da la
  versión original publicada; si importa la consolidada, adviértelo.

## 3. Jurisprudencia

Orden de autoridad: TJUE (en materias de Derecho UE) y TC (derechos fundamentales)
→ TS (doctrina jurisprudencial, art. 1.6 CC) → TSJ / AP (criterio territorial).

- TS y resto del CENDOJ: `buscar_sentencias(consulta, jurisdiccion, ...)`, ordenando
  por relevancia si buscas doctrina consolidada. Lee con `leer_sentencia(url,
  palabras_clave=...)` para traer el párrafo exacto, no 40.000 caracteres.
- TC: `buscar_tc` + `leer_tc(referencia, seccion='fundamentos'|'fallo')`.
- TJUE: `buscar_tjue` + `leer_tjue(asunto, seccion='fallo')`.
- Cuando tengas una cita concreta de otra fuente (un artículo doctrinal, la otra
  parte), ábrela con `buscar_por_cita` antes de usarla.

Busca también la jurisprudencia **contraria**: una nota que solo recoge lo favorable
no sirve para decidir. Si hay doctrina contradictoria entre Audiencias, dilo.

## 4. Doctrina administrativa (cuando aplique)

Tributario: DGT (`buscar_consultas_hacienda`, con tildes) y TEAC
(`buscar_doctrina_teac`); la doctrina REITERADA del TEAC vincula a los TEAR y a
toda la Administración tributaria (art. 239.8 LGT); las consultas vinculantes de
la DGT vinculan a los órganos de aplicación de los tributos (art. 89 LGT), y su
criterio se aplica a otros obligados con hechos idénticos. Laboral: convenio colectivo aplicable (`leer_convenio`). Local:
ordenanzas (`buscar_ordenanzas` + `leer_boletin`).

## 5. Plazos

Si hay un plazo en juego, calcúlalo con `computo_plazo` (días hábiles o naturales,
comunidad, fiestas locales) y explica el día inicial elegido. Señala si es de
caducidad o de prescripción y qué lo interrumpe o suspende.

## 6. Verificar antes de entregar

Pasa el borrador de la nota por `verificar_escrito(texto=...)`. Para cada cita
✓ comprueba que lo que afirmas coincide con el texto oficial; corrige o elimina las
✗ y ⚠. Si una sentencia del CENDOJ no se ha podido comprobar, márcala como tal en
la nota en vez de presentarla como verificada.

## 7. Entregable: nota de investigación

Usa esta estructura (adáptala si el usuario pide otra cosa):

```
NOTA DE INVESTIGACIÓN — <asunto>            Fecha: <hoy> · Fuentes consultadas: <hoy>

1. Cuestión planteada
2. Respuesta breve (3-5 líneas, con el grado de certeza)
3. Marco normativo vigente (precepto · vigente desde · texto relevante citado)
4. Jurisprudencia
   - Favorable: <tribunal, fecha, ROJ/ECLI, párrafo literal entre comillas>
   - Contraria o matizadora: …
5. Doctrina administrativa (si procede)
6. Plazos y requisitos procesales
7. Riesgos, lagunas y lo que falta por confirmar
8. Fuentes (lista con enlaces oficiales)
```

Reglas de estilo: cita literal solo lo que has leído en esta sesión; distingue
claramente entre lo que dice la fuente y tu valoración; fecha la nota, porque el
Derecho cambia.

Si el usuario va a redactar un escrito a continuación, ofrece `guia_escrito` con el
tipo de escrito y reutiliza la nota como fundamentos.

## Cuando una fuente falla

Si una fuente oficial está caída (la tool dice HTTP 5xx), indícalo en la nota y
continúa con el resto; no inventes lo que no pudiste leer. El CENDOJ es para
consulta documento a documento: no lances decenas de búsquedas para "barrer" un tema.
