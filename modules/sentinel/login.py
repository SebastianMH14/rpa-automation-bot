import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from config.settings import URL_LOGIN_SENTINEL, USUARIO_SENTINEL, PASSWORD_SENTINEL

logger = logging.getLogger("bot")


def login_sentinel(driver, wait) -> None:
    """
    Abre la página de login de Sentinel, ingresa credenciales y espera
    a que el botón de pruebas esté disponible.

    Raises:
        TimeoutException: si el login no carga el elemento esperado.
    """
    logger.info("=" * 60)
    logger.info("🔵 INICIANDO SESIÓN EN SENTINEL")
    logger.info("=" * 60)

    driver.get(URL_LOGIN_SENTINEL)

    wait.until(EC.presence_of_element_located(
        (By.ID, "Staff_Username"))
    ).send_keys(USUARIO_SENTINEL)

    driver.find_element(By.ID, "Staff_Password").send_keys(
        PASSWORD_SENTINEL + Keys.ENTER
    )

    wait.until(EC.presence_of_element_located((By.ID, "Button_Tests")))
    logger.info("✅ Login Sentinel exitoso | Usuario: %s", USUARIO_SENTINEL)

    wait.until(EC.element_to_be_clickable((By.ID, "Button_Tests"))).click()
    logger.info("📋 Accediendo a listado de pruebas")