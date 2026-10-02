# Evaluacion de iuris-mcp

`iuris_evaluation.xml` contiene 10 preguntas reales con respuesta unica y estable
(verificadas con las propias tools el 2026-10-02). Miden si un modelo, usando
solo este MCP, elige la herramienta correcta y lee la fuente oficial vigente.

Las tres primeras detectan especificamente el error que tuvo `buscar_articulo`
hasta la v0.2.0 (devolvia la redaccion ORIGINAL de 2001 en vez de la vigente).

## Ejecutar

Usa el script `evaluation.py` del skill **mcp-builder** (necesita
`ANTHROPIC_API_KEY` en el entorno y consume tokens de tu cuenta):

```bash
python <ruta-del-skill>/mcp-builder/scripts/evaluation.py -t stdio -c "C:\Users\crist\iuris-mcp-venv\Scripts\python.exe" -a server.py -m claude-sonnet-5-5 evals/iuris_evaluation.xml -o evals/informe.md
```

Si una respuesta deja de coincidir, primero comprueba si la norma ha cambiado
(p. ej. una reforma de la LEC): en ese caso se actualiza la respuesta, no el codigo.
