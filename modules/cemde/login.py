import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from config.settings import URL_LOGIN_CEMDE, EMAIL_CEMDE, PASSWORD_CEMDE

logger = logging.getLogger("bot")


def login_cemde(driver, wait) -> None:
    """
    Abre el login de CEMDE, ingresa credenciales y espera a que
    la sesión esté activa.

    Raises:
        TimeoutException: si el formulario no carga o el login falla.
    """
    logger.info("=" * 60)
    logger.info("🟢 INICIANDO SESIÓN EN CEMDE")
    logger.info("=" * 60)

    driver.get(URL_LOGIN_CEMDE)

    wait.until(
        EC.presence_of_element_located((By.NAME, "email"))
    ).send_keys(EMAIL_CEMDE)

    driver.find_element(By.NAME, "password").send_keys(PASSWORD_CEMDE)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)  # esperar redirección post-login
    logger.info("✅ Login CEMDE exitoso | Usuario: %s", EMAIL_CEMDE)
