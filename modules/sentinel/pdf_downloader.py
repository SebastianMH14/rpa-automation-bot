import logging
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger("bot")

_BASE_URL = "http://181.143.85.123"


def descargar_pdf_desde_iframe(driver, ruta_pdf: str) -> bool:
    """
    Localiza el iframe cuyo src contiene 'GetPdf', construye la URL absoluta,
    descarga el PDF reutilizando las cookies del navegador y lo guarda en disco.

    Args:
        driver   : instancia de Selenium WebDriver (ya autenticado en Sentinel).
        ruta_pdf : ruta absoluta donde se guardará el archivo .pdf.

    Returns:
        True si el PDF se guardó correctamente, False en cualquier otro caso.
    """
    logger.debug("Intentando descargar PDF desde iframe → %s", ruta_pdf)
    try:
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//iframe[contains(@src,'GetPdf')]")
            )
        )
        pdf_url = iframe.get_attribute("src")
        if not pdf_url.startswith("http"):
            pdf_url = _BASE_URL + pdf_url

        logger.debug("URL del PDF: %s", pdf_url)

        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        response = session.get(pdf_url, verify=False, timeout=30)
        content_type = response.headers.get("Content-Type", "")

        if response.status_code == 200 and "pdf" in content_type:
            with open(ruta_pdf, "wb") as f:
                f.write(response.content)
            logger.info(
                "✅ PDF guardado: %s (%.1f KB)",
                ruta_pdf, len(response.content) / 1024,
            )
            return True

        logger.warning(
            "⚠ Respuesta inesperada | Status: %d | Content-Type: %s",
            response.status_code, content_type,
        )

    except Exception as e:
        logger.error("❌ No se pudo descargar PDF desde iframe: %s",
                     e, exc_info=True)

    return False
