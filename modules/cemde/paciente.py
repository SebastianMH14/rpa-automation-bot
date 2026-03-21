import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from config.settings import URL_PACIENTES

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
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='search']"))
    )
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


def obtener_sede(driver, wait, fecha_busqueda: str) -> str | None:
    """
    En la pestaña de atenciones, busca la fila que coincide con `fecha_busqueda`
    (formato DD/MM/YYYY) y devuelve la sede correspondiente.
    """
    tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@href='#tab-citas']")))
    tab.click()
    time.sleep(2)

    filas = driver.find_elements(
        By.XPATH, "//table[@id='pacientes-table']//tbody/tr"
    )

    for fila in filas:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        if len(celdas) < 3:
            continue
        if fecha_busqueda in celdas[1].text.strip():
            sede = celdas[2].text.strip()
            logger.info("🏥 Sede encontrada: %s", sede)
            return sede

    logger.warning("⚠ No se encontró sede para fecha %s", fecha_busqueda)
    return None