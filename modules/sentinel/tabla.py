import logging
import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

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
    """
    Recorre todas las páginas de la tabla de Sentinel, descarga los PDFs
    de los pacientes que aplican y devuelve la lista de metadatos.

    En modo PRUEBA (CEDULAS_PRUEBA no vacío) se detiene en cuanto encuentra
    todas las cédulas del conjunto.

    Returns:
        Lista de dicts con claves: ruta, nombre, cedula, examen, fecha_atencion.
    """
    pdfs_descargados: list[dict] = []
    cedulas_encontradas: set[str] = set()
    pagina = 1
    total_procesadas = 0
    total_omitidas = 0
    modo_prueba = bool(CEDULAS_PRUEBA)

    while True:
        logger.info("─" * 50)
        logger.info("📄 Procesando página %d", pagina)

        wait.until(EC.presence_of_element_located((By.XPATH, "//rows/row")))
        time.sleep(2)

        total_filas = len(driver.find_elements(By.XPATH, "//rows/row"))
        logger.info("Filas encontradas en página %d: %d", pagina, total_filas)

        i = 0
        while i < total_filas:
            try:
                rows = driver.find_elements(By.XPATH, "//rows/row")
                if i >= len(rows):
                    logger.warning(
                        "⚠ Fila %d no disponible (total actual: %d)", i, len(rows))
                    break

                row = rows[i]
                cells = row.find_elements(By.XPATH, "./cell")

                if len(cells) < 19:
                    logger.debug(
                        "Fila %d omitida: solo %d celdas", i, len(cells))
                    total_omitidas += 1
                    i += 1
                    continue

                cedula = cells[8].text.strip().rstrip(".")
                nombre = cells[9].text.strip()
                fecha_atencion = cells[11].text.strip()

                logger.debug("Revisando fila %d | %s | %s | %s",
                             i, cedula, nombre, fecha_atencion)

                # --- Filtro modo prueba ---
                if modo_prueba and cedula not in CEDULAS_PRUEBA:
                    total_omitidas += 1
                    i += 1
                    continue

                if modo_prueba:
                    logger.info("🎯 Cédula de prueba encontrada: %s | %s | %s",
                                cedula, nombre, fecha_atencion)
                    cedulas_encontradas.add(cedula)
                    if cedulas_encontradas == CEDULAS_PRUEBA:
                        logger.info("✅ Todas las cédulas de prueba encontradas (%d/%d)",
                                    len(cedulas_encontradas), len(CEDULAS_PRUEBA))
                        return pdfs_descargados

                # --- Tipo de examen ---
                examen_raw = cells[18].get_attribute("tooltip") or ""
                examen = MAPEO_TIPOS_EXAMEN.get(examen_raw.strip().lower(), "")
                logger.debug("Examen | Raw: '%s' → '%s'",
                             examen_raw, examen or "(sin mapeo)")

                # --- Estado ---
                estado = next(
                    (cell.text.strip().upper()
                     for cell in cells
                     if cell.text.strip().upper() in ("CONFIRMADO", "RECONFIRMADO")),
                    None,
                )

                logger.info(
                    "Fila | %s | %s | examen: %s | fecha: %s | estado: %s",
                    nombre, cedula, examen or "(vacío)", fecha_atencion, estado or "(sin estado)",
                )

                if estado not in ("CONFIRMADO", "RECONFIRMADO"):
                    logger.info("⏭ Omitida: estado '%s'", estado)
                    total_omitidas += 1
                    i += 1
                    continue

                # --- Abrir informe ---
                total_procesadas += 1
                _abrir_informe(driver, wait, row)

                # --- Firmante ---
                firmante = _obtener_firmante(driver)
                if not firmante:
                    logger.warning(
                        "⚠ Sin firmante confirmado para %s | %s", nombre, cedula)

                # --- Rutas ---
                nombre_archivo = f"{cedula}_{nombre}".replace(
                    " ", "_") + ".pdf"
                carpeta_medico = firmante.replace(
                    " ", "_") if firmante else "SIN_FIRMANTE"
                carpeta_destino = os.path.join(DOWNLOAD_DIR, carpeta_medico)
                os.makedirs(carpeta_destino, exist_ok=True)
                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo)

                # --- Descarga ---
                if not descargar_pdf_desde_iframe(driver, ruta_pdf):
                    logger.warning(
                        "⚠ PDF no descargado para %s | %s", nombre, cedula)

                pdfs_descargados.append({
                    "ruta": ruta_pdf,
                    "nombre": nombre_archivo,
                    "cedula": cedula,
                    "examen": examen,
                    "fecha_atencion": fecha_atencion,
                })

                break

                # --- Volver a la tabla ---
                driver.back()
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//rows/row")))
                wait.until(lambda d: len(
                    d.find_elements(By.XPATH, "//rows/row")) > i)

            except Exception as e:
                logger.error("❌ Error en fila %d página %d: %s",
                             i, pagina, e, exc_info=True)

            finally:
                i += 1

        logger.info(
            "Página %d completada | Procesadas: %d | Omitidas: %d | PDFs: %d",
            pagina, total_procesadas, total_omitidas, len(pdfs_descargados),
        )

        # --- Paginación ---
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "span.nextPage")
            if "disabled" in next_btn.get_attribute("class"):
                logger.info("📄 Última página alcanzada")
                break
            logger.info("➡ Avanzando a página %d", pagina + 1)
            driver.execute_script("arguments[0].click();", next_btn)
            pagina += 1
            time.sleep(3)
        except Exception as e:
            logger.warning("⚠ No se pudo avanzar de página: %s", e)
            break

    logger.info("=" * 60)
    logger.info(
        "📊 RESUMEN SENTINEL | Páginas: %d | PDFs: %d | Cédulas: %d/%d",
        pagina, len(pdfs_descargados),
        len(cedulas_encontradas), len(
            CEDULAS_PRUEBA) if modo_prueba else total_procesadas,
    )
    logger.info("=" * 60)
    return pdfs_descargados
