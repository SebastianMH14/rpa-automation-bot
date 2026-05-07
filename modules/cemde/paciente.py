import logging
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from config.settings import URL_PACIENTES
from utils.fecha import parse_fecha

logger = logging.getLogger("bot")


def abrir_paciente(driver, wait, cedula: str) -> None:
    """
    Navega a la lista de pacientes, busca por cédula y abre el perfil.

    Raises:
        TimeoutException: si no se encuentra el paciente.
    """
    driver.get(URL_PACIENTES)
    time.sleep(3)

    inp = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='search']"))
    )
    cedula = re.sub(r"[^\d]", "", cedula)
    inp.clear()
    inp.send_keys(cedula)

    resultado = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH,
             f"//ul[@id='lista-pacientes']//a[contains(@class,'list-group-item') "
             f"and contains(.,'{cedula}')]")
        )
    )
    driver.execute_script("arguments[0].click();", resultado)
    logger.debug("Paciente abierto: %s", cedula)

    # ── NUEVO: esperar que el perfil esté completamente cargado ──
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//a[@href='#tab-citas']")
        )
    )
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//a[@href='#tab-notas-enfermeria']")
        )
    )
    logger.debug("Perfil del paciente %s completamente cargado", cedula)


def obtener_sede(driver, wait, fecha_busqueda: str) -> str | None:

    def _click_tab_citas():
        tab = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-citas']")))
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", tab)
        time.sleep(0.5)
        try:
            tab.click()
        except Exception:
            driver.execute_script("arguments[0].click();", tab)
        time.sleep(2)

    _click_tab_citas()

    # Verificar si la tabla está vacía y reintentar recargando
    MAX_INTENTOS = 3
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            script = """
            var dt = $('#pacientes-table').DataTable();
            return {
                search: dt.search(),
                page: dt.page(),
                pageLen: dt.page.len(),
                totalRows: dt.rows().count(),
                totalFiltered: dt.rows({search: 'applied'}).count()
            };
            """
            info = driver.execute_script(script)
            print(f"DataTable info: {info}")

            tbody = driver.find_element(
                By.XPATH, "//table[@id='pacientes-table']//tbody")
            contenido = tbody.get_attribute("innerHTML")

            if "No hay datos disponibles" in contenido:
                logger.warning(
                    "⚠ Tabla vacía en intento %d/%d — recargando página",
                    intento, MAX_INTENTOS
                )
                driver.refresh()
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//a[@href='#tab-citas']")))
                time.sleep(1)
                _click_tab_citas()
                continue

            # Tabla tiene datos — procesar filas
            break

        except Exception as e:
            logger.warning(
                "⚠ Error leyendo tbody en intento %d: %s", intento, e)
            time.sleep(2)
    else:
        logger.warning("⚠ Tabla siguió vacía tras %d intentos para fecha %s",
                       MAX_INTENTOS, fecha_busqueda)
        return None

    filas = driver.find_elements(
        By.XPATH, "//table[@id='pacientes-table']//tbody/tr"
    )

    for fila in filas:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        textos = [c.text.strip() for c in celdas]

        if len(textos) < 4:
            continue

        fecha_celda_raw = textos[2].split()[0]
        fecha_celda = parse_fecha(fecha_celda_raw)
        fecha_objetivo = parse_fecha(fecha_busqueda)

        if not fecha_celda or not fecha_objetivo:
            continue

        if fecha_celda.date() == fecha_objetivo.date():
            sede = textos[3].replace("\n", " ").strip()
            logger.info("🏥 Sede encontrada: %s", sede)
            return sede

    logger.warning("⚠ No se encontró sede para fecha %s", fecha_busqueda)
    return None


def seleccionar_sede(driver, wait, sede_objetivo: str) -> bool:
    """
    Abre el modal de sedes, busca la sede que coincida con sede_objetivo
    (coincidencia parcial, case-insensitive) y la selecciona.

    Args:
        sede_objetivo : nombre de la sede a seleccionar (ej: "BELLO", "LAURELES").

    Returns:
        True si se seleccionó correctamente, False si no se encontró.
    """
    if not sede_objetivo:
        logger.error(
            "⚠ No se encontro la sede de atencion, no se puede seleccionar sede.")
        return False

    # 1. Verificar si ya está en la sede correcta
    sede_actual = driver.find_element(
        By.CSS_SELECTOR, "a.btnCurrentSede"
    ).text.strip().upper()

    if sede_objetivo.upper() in sede_actual:
        logger.info("✅ Ya se encuentra en la sede: %s", sede_actual)
        return True

    logger.info("🏥 Sede actual: '%s' | Cambiando a: '%s'",
                sede_actual, sede_objetivo)

    # 2. Abrir modal de sedes
    btn_sede = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btnCurrentSede"))
    )
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", btn_sede)
    time.sleep(0.5)
    try:
        btn_sede.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn_sede)
        logger.debug("Botón sede clickeado via JS fallback")

    # 3. Esperar que cargue el modal con las sedes
    wait.until(
        EC.presence_of_element_located((By.ID, "containerSedesCambiar"))
    )
    time.sleep(1)

    # 4. Buscar la sede por coincidencia parcial en el h3
    cards = driver.find_elements(
        By.XPATH,
        f"//div[@id='containerSedesCambiar']//h3[contains(translate(., "
        f"'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), "
        f"'{sede_objetivo.upper()}')]"
    )

    if not cards:
        logger.error("❌ No se encontró sede '%s' en el modal", sede_objetivo)
        return False

    if len(cards) > 1:
        logger.warning("⚠ Múltiples sedes coinciden con '%s', seleccionando la primera: '%s'",
                       sede_objetivo, cards[0].text.strip())

    sede_encontrada = cards[0].text.strip()
    logger.info("🎯 Sede encontrada: '%s'", sede_encontrada)

    # 5. Hacer click en el <ins> del radio (iCheck no permite click directo al input)
    ins = cards[0].find_element(
        By.XPATH,
        "./ancestor::div[contains(@class,'card-sede')]//ins[contains(@class,'iCheck-helper')]"
    )
    driver.execute_script("arguments[0].click();", ins)
    time.sleep(1)

    # 6. Verificar que el radio quedó marcado
    radio = cards[0].find_element(
        By.XPATH,
        "./ancestor::div[contains(@class,'card-sede')]//input[@name='sede_cambiar']"
    )
    if not radio.is_selected():
        logger.warning(
            "⚠ Radio no marcado tras click en ins, reintentando via JS")
        driver.execute_script(
            "arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", radio)
        time.sleep(0.5)

    # 7. Confirmar cambio de sede
    btn_confirmar = wait.until(
        EC.element_to_be_clickable((By.ID, "btnConfirmaCambioSede"))
    )
    try:
        btn_confirmar.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn_confirmar)
        logger.debug("Botón confirmar sede clickeado via JS fallback")

    # 8. Esperar que el botón de sede actual se actualice con la nueva sede
    wait.until(
        EC.text_to_be_present_in_element(
            (By.CSS_SELECTOR, "a.btnCurrentSede"),
            # "LAURELES, ANTIOQUIA" → busca "LAURELES"
            sede_objetivo.split(",")[0].strip()
        )
    )

    logger.info("✅ Sede seleccionada y confirmada: '%s'", sede_encontrada)
    return True
