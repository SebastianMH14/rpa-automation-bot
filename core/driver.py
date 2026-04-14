import os
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from config.settings import DOWNLOAD_DIR


def crear_driver(timeout: int = 30) -> tuple[webdriver.Edge, WebDriverWait]:
    """
    Configura y devuelve (driver, wait) listos para usar.

    Returns:
        driver : instancia de Edge con preferencias de descarga.
        wait   : WebDriverWait asociado al driver con el timeout dado.
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = Options()
    options.add_argument("--start-maximized")
    options.add_experimental_option("prefs", {
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
        "download.default_directory": DOWNLOAD_DIR,
    })

    driver = webdriver.Edge(service=Service(), options=options)
    wait = WebDriverWait(driver, timeout)

    return driver, wait
