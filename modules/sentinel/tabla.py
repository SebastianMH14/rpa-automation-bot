from datetime import datetime
import logging
import os
import shutil
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from config.settings import (
    CEDULAS_PRUEBA,
    DOWNLOAD_DIR,
    MAPEO_TIPOS_EXAMEN,
    FECHA_LIMITE

)
from modules.sentinel.pdf_downloader import descargar_pdf_desde_iframe
from utils.validacion_informe import (
    encabezado_corresponde,
    parsear_encabezado,
    registrar_visita,
    validar_pdf,
)
logger = logging.getLogger("bot")

# Carpeta (dentro de DOWNLOAD_DIR) donde se aparta, sin borrarlo, un PDF que
# no corresponde al paciente. Se excluye del índice de PDFs existentes.
CARPETA_DESCARTADOS = "_DESCARTADOS"

if FECHA_LIMITE:
    try:
        FECHA_LIMITE = datetime.strptime(FECHA_LIMITE, "%d/%m/%Y")
    except ValueError:
        logger.error(
            "❌ FECHA_LIMITE inválida: '%s'. Use DD/MM/YYYY.", FECHA_LIMITE)

# Índice: clave = "YYYY-MM-DD/nombre_archivo.pdf" → ruta completa
# Así se distinguen el mismo examen en fechas distintas para un mismo paciente.
pdfs_existentes = {}

for root, dirs, files in os.walk(DOWNLOAD_DIR):
    dirs[:] = [d for d in dirs if d != CARPETA_DESCARTADOS]
    for file in files:
        fecha_dir = os.path.basename(root)  # carpeta inmediata = YYYY-MM-DD
        clave = f"{fecha_dir}/{file}"
        pdfs_existentes[clave] = os.path.join(root, file)
        # También indexamos solo por nombre para compatibilidad con código legado
        pdfs_existentes[file] = os.path.join(root, file)


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


def _descartar_pdf(ruta_pdf: str) -> None:
    """Aparta un PDF que no corresponde al paciente, para que no se vuelva a
    subir ni cuente como ya descargado. Se conserva como evidencia."""
    destino_dir = os.path.join(DOWNLOAD_DIR, CARPETA_DESCARTADOS)
    os.makedirs(destino_dir, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(
        destino_dir, f"{sello}_{os.path.basename(ruta_pdf)}")
    shutil.move(ruta_pdf, destino)
    logger.warning("🗑 PDF apartado en %s", destino)


def _leer_encabezado_informe(driver) -> tuple[str, str] | None:
    """('NOMBRE', 'ID') de 'Revisar informe - NOMBRE (ID)', o None si la
    pantalla no lo muestra con ese formato."""
    for el in driver.find_elements(
            By.XPATH, "//*[contains(text(),'Revisar informe')]"):
        encabezado = parsear_encabezado(el.text or "")
        if encabezado:
            return encabezado
    return None


def _informe_invalido(cedula, nombre, nombre_archivo, fecha_atencion,
                      examen, estado, motivo) -> dict:
    """Entrada para `subir_pdfs`: no se procesa, se registra como fallida."""
    return {
        "ruta": None,
        "nombre": nombre_archivo,
        "cedula": cedula,
        "examen": examen,
        "fecha_atencion": fecha_atencion,
        "estado": estado,
        "firmante": None,
        "invalido": f"Informe descartado, no se sube a CEMDE: {motivo}",
    }


def _firmante_desde_ruta(ruta_pdf: str) -> str | None:
    """
    Extrae el nombre del firmante del penúltimo componente de la ruta.
    Estructura esperada: …/NOMBRE_MEDICO/YYYY-MM-DD/archivo.pdf
    """
    partes = os.path.normpath(ruta_pdf).split(os.sep)
    # partes[-1] = archivo, partes[-2] = fecha, partes[-3] = médico
    if len(partes) >= 3:
        carpeta_medico = partes[-3]
        return carpeta_medico.replace("_", " ") if carpeta_medico != "SIN_FIRMANTE" else None
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
    pdfs: list[dict] = []
    total_omitidas = 0
    pagina = 1
    visitados: set = set()

    modo_una_sola = cedula_filtro is not None

    while True:
        logger.info("─" * 50)
        logger.info("📄 Procesando página %d", pagina)

        wait.until(EC.presence_of_element_located((By.XPATH, "//rows/row")))
        rows = driver.find_elements(By.XPATH, "//rows/row")

        logger.info("Filas visibles: %d", len(rows))

        for i in range(len(rows)):
            try:
                rows = driver.find_elements(By.XPATH, "//rows/row")
                row = rows[i]

                cells = row.find_elements(By.XPATH, "./cell")

                if len(cells) < 19:
                    total_omitidas += 1
                    continue

                cedula = cells[8].text.strip().rstrip(".")
                nombre = cells[9].text.strip()
                nombre = nombre.replace(",", "")
                fecha_atencion = cells[11].text.strip()

                if cedula_filtro and cedula != cedula_filtro:
                    total_omitidas += 1
                    continue

                if not CEDULAS_PRUEBA and FECHA_LIMITE:
                    try:
                        fecha_dt = datetime.strptime(
                            fecha_atencion, "%d/%m/%Y %H:%M:%S")
                        if fecha_dt.date() < FECHA_LIMITE.date():
                            logger.info(
                                "🛑 Fecha límite alcanzada, deteniendo proceso")
                            return pdfs
                    except ValueError:
                        total_omitidas += 1
                        continue

                examen_raw = cells[18].get_attribute("tooltip") or ""
                examen = MAPEO_TIPOS_EXAMEN.get(examen_raw.strip().lower(), "")

                estado = None
                for cell in cells:
                    texto = (cell.text or "").strip().upper()

                    if texto == "CONFIRMADO":
                        estado = "CONFIRMADO"
                        break
                    elif texto == "RECONFIRMADO":
                        estado = "RECONFIRMADO"
                        break
                    elif texto == "RECHAZADO":          # ← NUEVO
                        estado = "RECHAZADO"
                        break

                logger.info(
                    "Fila | %s | %s | examen: %s | fecha: %s | estado: %s",
                    nombre, cedula, examen or "(vacío)", fecha_atencion, estado or "(sin estado)"
                )

                if estado not in ("CONFIRMADO", "RECONFIRMADO", "RECHAZADO"):
                    total_omitidas += 1
                    if modo_una_sola:
                        return pdfs
                    continue

                # Sentinel repite filas entre páginas. Visitar de nuevo un
                # examen en la misma corrida es lo que ha devuelto informes de
                # otra persona (incidente 24/10/2026): se omite la repetición.
                if registrar_visita(visitados, cedula, examen, fecha_atencion):
                    logger.info(
                        "🔁 Fila repetida en esta corrida, se omite: %s | %s | %s",
                        nombre, cedula, fecha_atencion)
                    total_omitidas += 1
                    continue

                nombre_archivo = f"{cedula}_{nombre}_{examen}".replace(
                    " ", "_") + ".pdf"

                # La clave incluye la fecha para permitir el mismo examen en fechas distintas
                try:
                    fecha_carpeta_key = datetime.strptime(
                        fecha_atencion, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d")
                except ValueError:
                    fecha_carpeta_key = fecha_atencion

                clave_dedup = f"{fecha_carpeta_key}/{nombre_archivo}"

                if clave_dedup in pdfs_existentes:
                    ruta_pdf = pdfs_existentes[clave_dedup]

                    # Un PDF ya guardado pudo bajarse mal en una corrida
                    # anterior: se comprueba antes de reutilizarlo. Los
                    # rechazados no se suben, así que no se validan.
                    reutilizable = True
                    if estado in ("CONFIRMADO", "RECONFIRMADO"):
                        valido, motivo = validar_pdf(ruta_pdf, cedula, nombre)
                        if not valido:
                            reutilizable = False
                            logger.error(
                                "❌ PDF existente descartado: %s | %s | %s",
                                nombre_archivo, ruta_pdf, motivo)
                            _descartar_pdf(ruta_pdf)
                            del pdfs_existentes[clave_dedup]

                    if reutilizable:
                        firmante = _firmante_desde_ruta(ruta_pdf)

                        logger.info("⏭ PDF ya existe, se omite descarga: %s (firmante: %s)",
                                    nombre_archivo, firmante or "desconocido")
                        pdfs.append({
                            "ruta": ruta_pdf,
                            "nombre": nombre_archivo,
                            "cedula": cedula,
                            "examen": examen,
                            "fecha_atencion": fecha_atencion,
                            "estado": estado,
                            "firmante": firmante,   # ← NUEVO
                        })

                        if modo_una_sola:
                            return pdfs

                        continue

                # =========================
                # 🔽 PROCESAMIENTO
                # =========================
                row.click()

                wait.until(EC.element_to_be_clickable(
                    (By.ID, "Button_EditReport"))).click()

                try:
                    wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(.,'Aceptar')]"))).click()
                except:
                    pass

                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Revisar informe')]")))

                time.sleep(2)

                # El informe abierto debe ser el de la fila. Si el encabezado
                # "Revisar informe - NOMBRE (ID)" muestra a otra persona, no
                # se descarga. Si no se puede leer, queda la comprobación del PDF.
                encabezado = _leer_encabezado_informe(driver)
                if (encabezado and estado in ("CONFIRMADO", "RECONFIRMADO")):
                    valido, motivo = encabezado_corresponde(
                        cedula, nombre, encabezado[0], encabezado[1])
                    if not valido:
                        logger.error(
                            "❌ Informe equivocado en pantalla para %s | %s: %s",
                            nombre, cedula, motivo)
                        pdfs.append(_informe_invalido(
                            cedula, nombre, nombre_archivo, fecha_atencion,
                            examen, estado, motivo))
                        driver.back()
                        wait.until(EC.presence_of_element_located(
                            (By.XPATH, "//rows/row")))
                        continue

                firmante = _obtener_firmante(driver)

                carpeta_medico = firmante.replace(
                    " ", "_") if firmante else "SIN_FIRMANTE"
                fecha_carpeta = datetime.strptime(
                    fecha_atencion, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d")
                carpeta_destino = os.path.join(
                    DOWNLOAD_DIR, carpeta_medico, fecha_carpeta)
                os.makedirs(carpeta_destino, exist_ok=True)

                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo)

                # 🔽 SOLO SI NO EXISTE
                if not descargar_pdf_desde_iframe(driver, ruta_pdf):
                    logger.warning(
                        "⚠ PDF no descargado para %s | %s", nombre, cedula)
                    total_omitidas += 1
                    driver.back()
                    wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//rows/row")))
                    continue

                # Última barrera: el PDF descargado debe ser del paciente.
                if estado in ("CONFIRMADO", "RECONFIRMADO"):
                    valido, motivo = validar_pdf(ruta_pdf, cedula, nombre)
                    if not valido:
                        logger.error(
                            "❌ PDF descargado descartado para %s | %s: %s",
                            nombre, cedula, motivo)
                        _descartar_pdf(ruta_pdf)
                        pdfs.append(_informe_invalido(
                            cedula, nombre, nombre_archivo, fecha_atencion,
                            examen, estado, motivo))
                        driver.back()
                        wait.until(EC.presence_of_element_located(
                            (By.XPATH, "//rows/row")))
                        continue

                pdfs.append({
                    "ruta": ruta_pdf,
                    "nombre": nombre_archivo,
                    "cedula": cedula,
                    "examen": examen,
                    "fecha_atencion": fecha_atencion,
                    "estado": estado,
                    "firmante": firmante,   # ← NUEVO
                })

                driver.back()

                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//rows/row")))

                if modo_una_sola:
                    return pdfs

            except Exception as e:
                logger.error("❌ Error en fila %d: %s", i, e, exc_info=True)

        # =========================
        # 🔽 PAGINACIÓN (igual a tu función que funciona)
        # =========================
        try:
            next_buttons = driver.find_elements(
                By.CSS_SELECTOR, "span.nextPage")

            if not next_buttons:
                logger.info("📄 No hay botón de siguiente página")
                break

            next_button = next_buttons[0]

            if "disabled" in next_button.get_attribute("class"):
                logger.info("📄 Última página alcanzada")
                break

            logger.info("➡ Siguiente página")

            driver.execute_script("arguments[0].click();", next_button)

            pagina += 1
            time.sleep(3)

        except Exception as e:
            logger.warning("⚠ No se pudo avanzar de página: %s", e)
            break

    logger.info("Procesadas: %d | Omitidas: %d", len(pdfs), total_omitidas)
    return pdfs
