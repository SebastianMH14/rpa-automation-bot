import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
