import logging
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config.settings import SERVICIOS_EXAMEN

logger = logging.getLogger("bot")


def _abrir_nota_en_nueva_ventana(driver, wait, boton_ver) -> str:
    """
    Hace clic en el botón de ver nota, espera la nueva pestaña y cambia a ella.
    Devuelve el handle de la ventana principal para poder volver.
    """
    ventana_principal = driver.current_window_handle
    handles_antes = set(driver.window_handles)

    driver.execute_script("arguments[0].click();", boton_ver)

    wait.until(lambda d: set(d.window_handles) - handles_antes)
    nueva_ventana = (set(driver.window_handles) - handles_antes).pop()
    driver.switch_to.window(nueva_ventana)
    logger.debug("Cambiado a nueva ventana: %s", nueva_ventana)

    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//table[contains(@class,'table-condensed')]")
        )
    )
    return ventana_principal


def _cerrar_y_volver(driver, ventana_principal: str) -> None:
    driver.close()
    driver.switch_to.window(ventana_principal)
    logger.debug("Pestaña cerrada. Regresado a ventana principal")


def obtener_numero_sentinel(driver, wait, fecha_busqueda: str, tipo_examen: str) -> str | None:
    """
    Abre la pestaña de notas de enfermería, encuentra la nota que corresponde
    a `fecha_busqueda` y al servicio de `tipo_examen`, extrae y devuelve
    el número Sentinel del campo de observaciones.

    Solo aplica para exámenes HOLTER y MAPA.

    Args:
        driver         : instancia de Selenium WebDriver.
        wait           : WebDriverWait asociado.
        fecha_busqueda : fecha en formato DD/MM/YYYY (solo la parte de día).
        tipo_examen    : "HOLTER" o "MAPA".

    Returns:
        El número Sentinel como string, o None si no se encontró.
    """
    # if tipo_examen not in ("HOLTER", "MAPA"):
    #     return None

    logger.debug(
        "Buscando nota de enfermería para examen tipo %s", tipo_examen)

    tab_notas = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-notas-enfermeria']"))
    )
    tab_notas.click()

    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//table[@id='table']//tbody/tr"))
    )

    filas_notas = driver.find_elements(
        By.XPATH, "//table[@id='table']//tbody/tr")
    logger.debug("Filas de notas encontradas: %d", len(filas_notas))

    servicio_esperado = SERVICIOS_EXAMEN.get(tipo_examen.upper(), "").upper()

    for fila in filas_notas:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        if len(celdas) < 3:
            continue

        fecha_tabla = celdas[0].text.strip()
        logger.debug("Comparando fecha nota: '%s' con '%s'",
                     fecha_busqueda, fecha_tabla)

        if fecha_busqueda != fecha_tabla:
            continue

        boton_ver = fila.find_element(
            By.XPATH, ".//a[contains(@href,'notasEnfermerias')]"
        )

        ventana_principal = _abrir_nota_en_nueva_ventana(
            driver, wait, boton_ver)
        logger.info("📝 Nota de enfermería abierta para fecha %s",
                    fecha_busqueda)

        # Leer el servicio registrado en la nota
        servicio_nota = driver.find_element(
            By.XPATH,
            "//td[contains(text(),'Servicio')]/following-sibling::td//input",
        ).get_attribute("value").strip().upper()

        logger.info("Servicio en nota: '%s' | Esperado: '%s'",
                    servicio_nota, servicio_esperado)

        # Validar que el servicio coincide con el examen
        if servicio_esperado not in servicio_nota:
            logger.warning(
                "⚠ Servicio NO coincide, buscando siguiente nota | Nota: '%s' | Examen: '%s'",
                servicio_nota, tipo_examen,
            )
            _cerrar_y_volver(driver, ventana_principal)
            continue

        logger.info("✅ Servicio coincide | Nota: '%s' | Examen: '%s'",
                    servicio_nota, tipo_examen)

        # Extraer número Sentinel de las observaciones
        observaciones = driver.find_element(
            By.CLASS_NAME, "observaciones_nota_enfermeria"
        ).text

        diagnostico_raw = driver.find_element(
            By.XPATH,  "//th[contains(text(),'Diagnóstico Principal')]/following-sibling::td//textarea").get_attribute("value").strip()

        codigo_diagnostico = diagnostico_raw.split("-")[0].strip()

        logger.info("🧾 Diagnóstico extraído: %s", codigo_diagnostico)

        _cerrar_y_volver(driver, ventana_principal)

        match = re.search(r"SENTINEL\s*#\s*(\d+)",
                          observaciones, re.IGNORECASE)
        if match:
            numero = match.group(1)
            logger.info("🔢 Número Sentinel extraído: %s", numero)
            return {"numero_sentinel": numero, "codigo_diagnostico": codigo_diagnostico}
        elif codigo_diagnostico:
            logger.warning(
                "⚠ No se encontró número Sentinel pero se extrajo diagnóstico: %s",
                codigo_diagnostico,
            )
            return {"numero_sentinel": None, "codigo_diagnostico": codigo_diagnostico}
            

        logger.warning("⚠ No se encontró número Sentinel en las observaciones")
        return None  # nota correcta pero sin número → no seguir buscando

    logger.warning(
        "⚠ No se encontró nota de enfermería válida para fecha %s | examen: %s",
        fecha_busqueda, tipo_examen,
    )
    raise Exception("Nota de enfermería no encontrada para fecha {} y examen {}".format(
        fecha_busqueda, tipo_examen
    ))
    # return None
