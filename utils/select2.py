from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.action_chains import ActionChains
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys


logger = logging.getLogger("bot")


def buscar_opcion_select(
    driver,
    select_id: str,
    texto_buscar: str,
    fecha_buscar: str | None = None,
    timeout: int = 10,
) -> bool:
    """
    Abre un desplegable Select2 y selecciona la opción que coincida con
    `texto_buscar` (y opcionalmente con `fecha_buscar`).

    Args:
        driver       : instancia de Selenium WebDriver.
        select_id    : valor del atributo aria-labelledby sin el prefijo 'select2-' ni '-container'.
        texto_buscar : texto a buscar dentro de las opciones (case-insensitive, todas las palabras).
        fecha_buscar : fragmento de fecha que también debe estar presente en la opción (opcional).
        timeout      : segundos máximos de espera.

    Returns:
        True si se seleccionó la opción, False en caso contrario.
    """
    logger.debug(
        "Buscando opción en select2 '%s': '%s' (fecha: %s)",
        select_id, texto_buscar, fecha_buscar or "N/A",
    )
    try:
        trigger = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 f"[aria-labelledby='select2-{select_id}-container']")
            )
        )
        trigger.click()

        opciones = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, ".select2-results__option")
            )
        )

        palabras = texto_buscar.lower().split()
        logger.debug("Revisando %d opciones en select2 '%s'",
                     len(opciones), select_id)

        for opcion in opciones:
            texto = opcion.text.strip()
            if texto.lower().startswith("seleccione"):
                continue
            texto_lower = texto.lower()
            if not all(p in texto_lower for p in palabras):
                continue
            if fecha_buscar and fecha_buscar not in texto:
                continue
            opcion.click()
            logger.info("✅ Opción seleccionada en '%s': %s", select_id, texto)
            return True

        logger.warning(
            "⚠ Opción no encontrada en select2 '%s' | Buscado: '%s' | Fecha: '%s'",
            select_id, texto_buscar, fecha_buscar or "N/A",
        )
        return False

    except Exception as e:
        logger.error("❌ Error en select2 '%s': %s",
                     select_id, e, exc_info=True)
        return False


def _limpiar_nombre_firmante(nombre_raw: str) -> str:
    """
    Limpia el nombre del firmante eliminando:
    - Sufijos entre paréntesis: '(CEMDE)', '(Clínica X)', etc.
    - Prefijos de cargo conocidos: 'Cardiólogo/a', 'Dr.', 'Dra.', etc.

    Ejemplos:
        'Cardióloga Luz Adriana Ocampo A. (CEMDE)'  →  'Luz Adriana Ocampo A.'
        'Dr. Juan Pérez (CEMDE)'                     →  'Juan Pérez'
        'Eiman Damian Moreno Pallares'               →  'Eiman Damian Moreno Pallares'
    """
    # 1. Quitar todo lo que esté entre paréntesis (incluyendo los paréntesis)
    nombre = re.sub(r"\(.*?\)", "", nombre_raw).strip()

    # 2. Quitar prefijos de cargo al inicio (case-insensitive)
    prefijos = r"^(Dr\.?|Dra\.?|Cardiólog[ao]|Médic[ao]|Enfermer[ao]|Tecnólog[ao]|Especialista)\s+"
    nombre = re.sub(prefijos, "", nombre, flags=re.IGNORECASE).strip()

    return nombre


def _normalizar_nombre_busqueda(nombre: str) -> str:
    """
    Reduce el nombre a los primeros 3 tokens para evitar fallos por
    apellidos abreviados o incompletos.

    'Luz Adriana Ocampo A.'        →  'Luz Adriana Ocampo'
    'Eiman Damian Moreno Pallares' →  'Eiman Damian Moreno'
    'Juan Pérez'                   →  'Juan Pérez'
    """
    tokens = nombre.split()
    # Quitar tokens que sean solo una letra seguida de punto (abreviaciones)
    tokens = [t for t in tokens if not re.match(
        r"^[A-ZÁÉÍÓÚÑa-záéíóúñ]\.$", t)]
    return " ".join(tokens[:3])


def buscar_opcion_select_lectura(
    driver,
    select_id: str,
    texto_buscar: str,
    fecha_buscar: str | None = None,
    timeout: int = 10,
) -> bool:
    """
    Busca y selecciona una opción en un Select2 con carga AJAX.

    Args:
        driver       : instancia de Selenium WebDriver.
        select_id    : id base del select2 (ej: 'usuario_lectura').
        texto_buscar : texto a buscar en las opciones (case-insensitive).
        fecha_buscar : fragmento de fecha adicional para filtrar (opcional).
        timeout      : segundos máximos de espera.

    Returns:
        True si se seleccionó la opción, False en caso contrario.
    """

    TEXTOS_INVALIDOS = {
        "cargando...",
        "searching...",
        "buscando...",
        "loading more results...",
    }

    css_container = f"[aria-labelledby='select2-{select_id}-container']"
    css_search = ".select2-search--dropdown .select2-search__field"
    css_results = f"#select2-{select_id}-results .select2-results__option"
    css_open = ".select2-container--open"

    try:
        # ── 1. Abrir dropdown ─────────────────────────────────────────────
        trigger = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_container))
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", trigger
        )
        trigger = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, css_container))
        )
        try:
            trigger.click()
        except Exception:
            driver.execute_script("arguments[0].click();", trigger)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_open))
        )

        # ── 2. Escribir en el campo de búsqueda ───────────────────────────
        search_input = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css_search))
        )
        search_input.clear()
        search_input.send_keys(texto_buscar)

        # ── 3. Esperar resultados AJAX reales (ignorar "Cargando...") ─────
        def resultados_reales(d):
            elementos = d.find_elements(By.CSS_SELECTOR, css_results)
            textos = [e.text.strip().lower()
                      for e in elementos if e.text.strip()]
            if not textos:
                return False
            validos = [t for t in textos if t not in TEXTOS_INVALIDOS]
            return elementos if validos else False

        opciones = WebDriverWait(driver, timeout).until(resultados_reales)

        # ── 4. Localizar opción objetivo ──────────────────────────────────
        palabras = texto_buscar.lower().split()
        opcion_objetivo = None

        for opcion in opciones:
            try:
                texto = opcion.text.strip()
                texto_lower = texto.lower()

                if not texto or texto_lower in TEXTOS_INVALIDOS:
                    continue
                if texto_lower.startswith("seleccione"):
                    continue
                if "no results" in texto_lower or "sin resultado" in texto_lower:
                    break
                if not all(p in texto_lower for p in palabras):
                    continue
                if fecha_buscar and fecha_buscar not in texto:
                    continue

                opcion_objetivo = opcion
                break

            except StaleElementReferenceException:
                continue

        if opcion_objetivo is None:
            logger.warning(
                "⚠ Opción no encontrada en select2 '%s' | Buscado: '%s' | Fecha: '%s'",
                select_id, texto_buscar, fecha_buscar or "N/A",
            )
            return False

        # ── 5. Scroll a la opción ─────────────────────────────────────────
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", opcion_objetivo
        )
        time.sleep(0.3)

        # ── 6. Click con fallbacks ────────────────────────────────────────
        seleccionado = False

        # Intento 1: click normal
        if not seleccionado:
            try:
                opcion_objetivo.click()
                WebDriverWait(driver, 3).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_open))
                )
                seleccionado = True
            except Exception:
                pass

        # Intento 2: Enter en el input de búsqueda
        if not seleccionado:
            try:
                search = driver.find_element(By.CSS_SELECTOR, css_search)
                driver.execute_script("arguments[0].focus();", search)
                time.sleep(0.1)
                search.send_keys(Keys.ENTER)
                WebDriverWait(driver, 3).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_open))
                )
                seleccionado = True
            except Exception:
                pass

        # Intento 3: ActionChains
        if not seleccionado:
            try:
                ActionChains(driver)\
                    .move_to_element(opcion_objetivo)\
                    .pause(0.2)\
                    .click()\
                    .perform()
                WebDriverWait(driver, 3).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_open))
                )
                seleccionado = True
            except Exception:
                pass

        if not seleccionado:
            logger.error(
                "❌ Opción encontrada pero no se pudo seleccionar en '%s': '%s'",
                select_id, texto_buscar,
            )
            return False

        # ── 7. Validar texto renderizado ──────────────────────────────────
        texto_final = driver.find_element(
            By.ID, f"select2-{select_id}-container"
        ).text.strip()

        logger.info(
            "✅ Opción seleccionada en '%s': '%s'", select_id, texto_final
        )
        return True

    except TimeoutException as e:
        logger.error(
            "❌ Timeout en select2 '%s': %s", select_id, e, exc_info=True
        )
        return False

    except Exception as e:
        logger.error(
            "❌ Error en select2 '%s': %s", select_id, e, exc_info=True
        )
        return False
