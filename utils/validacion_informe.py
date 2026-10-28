"""
Comprobaciones para evitar subir a CEMDE un informe que no es del paciente.

Contexto (incidente 24/10/2026): en algunas visitas Sentinel devolvió el
informe de otra persona y el bot lo guardó con el nombre del paciente de la
fila. Aquí vive la lógica pura (sin Selenium) que decide si un informe
corresponde a la fila, y el registro de visitas para no abrir dos veces la
misma fila en una corrida (la visita repetida es lo que dispara el problema).
"""
import re
import unicodedata

# Partículas que no sirven para identificar a una persona.
_PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"}

# Marca con la que se reemplaza el carácter "�" que a veces deja la
# extracción de texto del PDF en lugar de una letra con tilde o la Ñ.
_COMODIN = "#"


def solo_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _normalizar(texto: str) -> str:
    texto = (texto or "").replace("�", _COMODIN)
    texto = unicodedata.normalize("NFD", texto.upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(rf"[^A-Z0-9{_COMODIN}]+", " ", texto).strip()


def _tokens_nombre(nombre: str) -> list[str]:
    return [t for t in _normalizar(nombre).split()
            if len(t) >= 3 and t not in _PARTICULAS]


def _palabra_coincide(token: str, palabra: str) -> bool:
    if token == palabra:
        return True
    return (
        _COMODIN in palabra
        and len(token) == len(palabra)
        and all(p == _COMODIN or p == t for t, p in zip(token, palabra))
    )


def _tokens_presentes(tokens: list[str], texto: str) -> int:
    palabras = set(_normalizar(texto).split())
    return sum(any(_palabra_coincide(t, p) for p in palabras) for t in tokens)


def _minimo_coincidencias(tokens: list[str]) -> int:
    # 3 tokens (o todos, si el nombre es más corto) es lo bastante exigente
    # para que dos personas distintas con un apellido en común no coincidan.
    return min(3, len(tokens))


def extraer_id_paciente(texto_pdf: str) -> str | None:
    """Dígitos de 'ID paciente: ...' en el informe. '' si el campo está vacío,
    None si el informe no tiene ese campo."""
    m = re.search(r"ID paciente:[ \t]*([^\s]*)", texto_pdf or "")
    return solo_digitos(m.group(1)) if m else None


def informe_corresponde(cedula: str, nombre: str, texto_pdf: str) -> tuple[bool, str]:
    """
    El informe corresponde al paciente de la fila si el ID del PDF coincide
    con la cédula, o —cuando el ID está mal digitado en Sentinel— si el
    nombre del paciente aparece en el informe.
    """
    id_fila = solo_digitos(cedula)
    id_pdf = extraer_id_paciente(texto_pdf)
    if id_pdf and id_fila and id_pdf == id_fila:
        return True, "el ID coincide"

    tokens = _tokens_nombre(nombre)
    presentes = _tokens_presentes(tokens, texto_pdf)
    if tokens and presentes >= _minimo_coincidencias(tokens):
        return True, f"el nombre coincide (ID en el PDF: {id_pdf or 'vacío'})"

    return False, (
        f"no corresponde al paciente: cédula de la fila {id_fila or '(vacía)'}, "
        f"ID dentro del PDF {id_pdf if id_pdf is not None else '(sin campo)'}, "
        f"{presentes} de {len(tokens)} palabras del nombre presentes"
    )


def encabezado_corresponde(cedula: str, nombre: str,
                           nombre_encabezado: str, id_encabezado: str) -> tuple[bool, str]:
    """Igual criterio, para 'Revisar informe - NOMBRE (ID)' de la pantalla."""
    id_fila, id_enc = solo_digitos(cedula), solo_digitos(id_encabezado)
    if id_enc and id_fila and id_enc == id_fila:
        return True, "el ID coincide"

    tokens = _tokens_nombre(nombre)
    presentes = _tokens_presentes(tokens, nombre_encabezado)
    if tokens and presentes >= _minimo_coincidencias(tokens):
        return True, "el nombre coincide"

    return False, (
        f"el informe abierto en pantalla es de '{nombre_encabezado}' ({id_encabezado}) "
        f"y la fila es la cédula {id_fila} ({presentes} de {len(tokens)} palabras del nombre)"
    )


def parsear_encabezado(texto: str) -> tuple[str, str] | None:
    """('NOMBRE', 'ID') de un texto 'Revisar informe - NOMBRE (ID)'."""
    m = re.search(r"Revisar informe\s*-\s*([^\n(]+?)\s*\(([^)\n]*)\)", texto or "")
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def verificar_dependencias() -> None:
    """Falla de inmediato si falta pypdf. Sin esto, una instalación sin la
    dependencia haría parecer ilegibles todos los PDFs y se apartarían todos."""
    import pypdf  # noqa: F401


def leer_texto_primera_pagina(ruta: str) -> str:
    from pypdf import PdfReader  # import perezoso: solo hace falta al validar
    return PdfReader(ruta).pages[0].extract_text() or ""


def validar_pdf(ruta: str, cedula: str, nombre: str) -> tuple[bool, str]:
    """
    Lee el PDF y comprueba que sea del paciente. Si no se puede leer, el
    resultado es NO válido: es preferible no subir un informe a subir uno que
    no se pudo comprobar (se reintenta en la próxima corrida). Una dependencia
    faltante no es un PDF ilegible: ese error se propaga.
    """
    try:
        texto = leer_texto_primera_pagina(ruta)
    except ImportError:
        raise
    except Exception as e:
        return False, f"no se pudo leer el PDF para verificarlo ({type(e).__name__}: {e})"
    return informe_corresponde(cedula, nombre, texto)


def registrar_visita(visitados: set, cedula: str, examen: str, fecha_atencion: str) -> bool:
    """
    Marca el examen como visitado en esta corrida. Devuelve True si YA se había
    visitado. Sentinel repite filas entre páginas, y en las visitas repetidas
    es donde se han abierto informes de otra persona.
    """
    # La cédula se compara tal cual (sin la coma/punto final que Sentinel a
    # veces agrega): quedarse solo con dígitos mezclaría cédulas alfanuméricas.
    clave = (cedula.strip().rstrip(".,").upper(), examen, fecha_atencion.strip())
    if clave in visitados:
        return True
    visitados.add(clave)
    return False
