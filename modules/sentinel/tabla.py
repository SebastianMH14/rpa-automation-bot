import logging
import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from config.settings import (
    CEDULAS_PRUEBA,
    DOWNLOAD_DIR,
    MAPEO_TIPOS_EXAMEN,
)
from modules.sentinel.pdf_downloader import descargar_pdf_desde_iframe

logger = logging.getLogger("bot")


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _obtener_firmante(driver) -> str | None:
    """Lee la tabla de firmas y devuelve el nombre del médico confirmado."""
    filas = driver.find_elements(
        By.XPATH,
        "//editlist[@id='Report_SignaturesTable']//rows/row",
    )
    logger.debug("Revisando %d filas de firmas", len(filas))
    for fila in filas:
        celdas = fila.find_elements(By.XPATH, "./cell")
        if len(celdas) < 5:
            continue
        decision = celdas[4].text.strip().lower()
        if decision in ("confirmado", "reconfirmado"):
            firmante = celdas[1].text.strip()
            logger.info("✅ Firmante: %s (decisión: %s)", firmante, decision)
            return firmante
    return None


def _abrir_informe(driver, wait, row) -> bool:
    """
    Hace clic en la fila y luego en 'Revisar informe'.
    Devuelve True si se abrió correctamente.
    """
    row.click()
    try:
        btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(text(),'Revisar informe')]")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
        time.sleep(0.5)
        btn.click()
        logger.info("✅ Clic en 'Revisar informe'")
    except Exception:
        btn = driver.find_element(
            By.XPATH, "//*[contains(text(),'Revisar informe')]"
        )
        driver.execute_script("arguments[0].click();", btn)
        logger.info("✅ Clic en 'Revisar informe' (JS fallback)")

    # Aceptar diálogo opcional
    try:
        wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(.,'Aceptar')]")
            )
        ).click()
        logger.debug("Diálogo de confirmación aceptado")
    except Exception:
        logger.debug("Sin diálogo de confirmación")

    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'Revisar informe')]")
        )
    )
    time.sleep(2)
    return True


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------

def procesar_tabla_sentinel(driver, wait) -> list[dict]:
    pdfs_descargados: list[dict] = []
    modo_prueba = bool(CEDULAS_PRUEBA)

    if modo_prueba:
        logger.info("🎯 Modo prueba: buscando %d cédulas directamente | %s",
                    len(CEDULAS_PRUEBA), CEDULAS_PRUEBA)
        for cedula in CEDULAS_PRUEBA:
            logger.info("🔍 Buscando cédula: %s", cedula)
            _buscar_cedula(driver, wait, cedula)
            pdfs = _procesar_paginas(driver, wait, cedula_filtro=cedula)
            pdfs_descargados.extend(pdfs)
            logger.info("✅ Cédula %s | PDFs descargados: %d",
                        cedula, len(pdfs))
    else:
        pdfs_descargados = _procesar_paginas(driver, wait)

    logger.info("=" * 60)
    logger.info("📊 RESUMEN SENTINEL | PDFs totales: %d", len(pdfs_descargados))
    logger.info("=" * 60)
    return pdfs_descargados


def _buscar_cedula(driver, wait, cedula: str) -> None:
    """Escribe la cédula en el buscador y ejecuta la búsqueda."""
    input_busqueda = wait.until(
        EC.presence_of_element_located((By.ID, "Criterion_Id"))
    )
    input_busqueda.clear()
    input_busqueda.send_keys(cedula)
    input_busqueda.send_keys(Keys.ENTER)
    wait.until(
        EC.text_to_be_present_in_element(
            (By.XPATH, "//rows/row[1]/cell[9]"), cedula
        )
    )
    logger.debug("🔎 Búsqueda ejecutada para cédula: %s", cedula)


def _procesar_paginas(driver, wait, cedula_filtro: str | None = None) -> list[dict]:
    """
    Procesa filas visibles. 
    Si cedula_filtro está presente, solo procesa la PRIMERA fila válida y retorna.
    """
    pdfs: list[dict] = []
    total_omitidas = 0
    # ← en búsqueda directa, solo 1 resultado
    modo_una_sola = cedula_filtro is not None

    rows = driver.find_elements(By.XPATH, "//rows/row")
    logger.info("Filas visibles: %d", len(rows))

    i = 0
    while i < len(rows):
        try:
            rows = driver.find_elements(By.XPATH, "//rows/row")
            if i >= len(rows):
                break

            row = rows[i]
            cells = row.find_elements(By.XPATH, "./cell")

            if len(cells) < 19:
                logger.debug("Fila %d omitida: solo %d celdas", i, len(cells))
                total_omitidas += 1
                i += 1
                continue

            cedula = cells[8].text.strip().rstrip(".")
            nombre = cells[9].text.strip()
            fecha_atencion = cells[11].text.strip()

            if cedula_filtro and cedula != cedula_filtro:
                print(
                    f"⏭ Fila {i} omitida: cédula '{cedula}' no coincide con filtro '{cedula_filtro}'")
                total_omitidas += 1
                i += 1
                continue

            examen_raw = cells[18].get_attribute("tooltip") or ""
            examen = MAPEO_TIPOS_EXAMEN.get(examen_raw.strip().lower(), "")
            if not examen:
                logger.warning(
                    "⚠ Sin mapeo para examen: '%s' | %s", examen_raw, cedula)

            estado = next(
                (cell.text.strip().upper()
                 for cell in cells
                 if cell.text.strip().upper() in ("CONFIRMADO", "RECONFIRMADO")),
                None,
            )

            logger.info("Fila | %s | %s | examen: %s | fecha: %s | estado: %s",
                        nombre, cedula, examen or "(vacío)", fecha_atencion, estado or "(sin estado)")

            if estado not in ("CONFIRMADO", "RECONFIRMADO"):
                logger.info("⏭ Omitida: estado '%s'", estado)
                total_omitidas += 1
                i += 1
                # En modo búsqueda directa, si esta fila no aplica tampoco seguimos
                if modo_una_sola:
                    logger.info(
                        "⏭ Modo búsqueda: sin resultado válido para cédula %s", cedula_filtro)
                    break
                continue

            _abrir_informe(driver, wait, row)

            firmante = _obtener_firmante(driver)
            if not firmante:
                logger.warning(
                    "⚠ Sin firmante confirmado para %s | %s", nombre, cedula)

            nombre_archivo = f"{cedula}_{nombre}".replace(" ", "_") + ".pdf"
            carpeta_medico = firmante.replace(
                " ", "_") if firmante else "SIN_FIRMANTE"
            carpeta_destino = os.path.join(DOWNLOAD_DIR, carpeta_medico)
            os.makedirs(carpeta_destino, exist_ok=True)
            ruta_pdf = os.path.join(carpeta_destino, nombre_archivo)

            if not descargar_pdf_desde_iframe(driver, ruta_pdf):
                logger.warning(
                    "⚠ PDF no descargado para %s | %s", nombre, cedula)

            pdfs.append({
                "ruta": ruta_pdf,
                "nombre": nombre_archivo,
                "cedula": cedula,
                "examen": examen,
                "fecha_atencion": fecha_atencion,
            })

            driver.back()
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//rows/row")))

            # ← En modo búsqueda directa: procesar solo este resultado y salir
            if modo_una_sola:
                logger.info(
                    "✅ Modo búsqueda: primer resultado procesado para cédula %s", cedula_filtro)
                break

            wait.until(lambda d: len(d.find_elements(
                By.XPATH, "//rows/row")) >= len(pdfs) + total_omitidas)

        except Exception as e:
            logger.error("❌ Error en fila %d: %s", i, e, exc_info=True)
        finally:
            i += 1

    logger.info("Procesadas: %d | Omitidas: %d", len(pdfs), total_omitidas)
    return pdfs
