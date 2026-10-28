"""Compatibilidad selectolax 0.4.x / 1.x para todo el repo.

selectolax 1.0 elimino el backend Modest: `from selectolax.parser import
HTMLParser` lanza ImportError. El backend actual es lexbor (LexborHTMLParser)
con una API casi identica. Importa siempre desde aqui:

    from common._selectolax import HTMLParser

y funciona con cualquier version instalada (0.3.x, 0.4.x, 1.x).
"""

try:  # selectolax >= 1.0 (backend lexbor, el mantenido)
    from selectolax.lexbor import LexborHTMLParser as HTMLParser
except ImportError:  # selectolax < 1.0 (backend Modest clasico)
    from selectolax.parser import HTMLParser

__all__ = ["HTMLParser"]
