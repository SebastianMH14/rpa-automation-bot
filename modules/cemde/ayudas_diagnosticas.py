import logging
import time
from selenium.common import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from config.settings import SERVICIOS_EXAMEN, SERVICIO_DEFAULT
from modules.cemde.paciente import abrir_paciente, obtener_sede, seleccionar_sede
from modules.cemde.notas_enfermeria import agregar_nota_aclaratoria_rechazado, obtener_numero_sentinel
from utils.select2 import buscar_opcion_select, _limpiar_nombre_firmante, _normalizar_nombre_busqueda, buscar_opcion_select_lectura
from utils.fecha import fecha_solo_dia, sentinel_a_input
from utils.radio import marcar_radio
from utils.fecha import parse_fecha
from utils.upload_report import UploadReport
from datetime import datetime
import os

logger = logging.getLogger("bot")


def _abrir_formulario_otros_ad(driver, wait, fecha_examen: str, tipo_examen: str) -> bool:
    """
    Navega a la pestaña de ayudas diagnósticas → otros AD y abre el formulario.

    Args:
        driver: WebDriver instance
        wait: WebDriverWait instance
        fecha_examen: Fecha del examen a cargar (formato 'YYYY-MM-DD')
        nombre_examen: Nombre del examen a cargar (ej: 'MONITOREO AMBULATORIO DE PRESIÓN ARTERIAL SISTEMICA')

    Returns:
        True si se abrió el formulario (flujo normal),
        False si el examen ya existe (proceso omitido).
    """
    tab_ayudas = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-ayudas-diagnosticas']"))
    )
    tab_ayudas.click()
    time.sleep(2)

    tab_otros = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//a[@href='#tab-otros-ad']"))
    )
    tab_otros.click()
    time.sleep(2)

    # ── Validación: revisar si el tipo de examen ya fue cargado ──────────────
    servicio_esperado = SERVICIOS_EXAMEN.get(tipo_examen.upper(), "").upper()

    # 1. Buscar si existe una pestaña con el nombre del examen
    tabs_ad = driver.find_elements(
        By.XPATH,
        "//div[contains(@class,'portlet-title')]//ul[contains(@class,'nav-tabs')]//a[@data-toggle='tab']"
    )

    tab_examen = None
    for tab in tabs_ad:
        if tab.text.strip().upper() == servicio_esperado:
            tab_examen = tab
            break

    if tab_examen is not None:
        logger.debug(
            f"Pestaña encontrada para '{servicio_esperado}', verificando registros existentes...")

        # 2. Hacer clic en la pestaña para cargar su tabla
        tab_examen.click()
        time.sleep(1.5)

        # 3. Buscar filas en la tabla activa dentro de ese tab
        tab_href = tab_examen.get_attribute(
            "href").split("#")[-1]  # ej: 'tab-otroAD2'
        filas = driver.find_elements(
            By.XPATH,
            f"//div[@id='{tab_href}']//table[contains(@class,'table')]//tbody//tr"
        )

        for fila in filas:
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) < 2:
                continue

            fecha_celda_raw = celdas[0].text.strip()
            examen_celda = celdas[1].text.strip().upper()

            fecha_celda = parse_fecha(fecha_celda_raw)
            fecha_objetivo = parse_fecha(fecha_examen)

            if not fecha_celda or not fecha_objetivo:
                logger.warning(f"No se pudo parsear fecha: {fecha_celda_raw}")
                continue

            if fecha_celda.date() == fecha_objetivo.date() and examen_celda == servicio_esperado:
                logger.warning(
                    f"El examen '{servicio_esperado}' con fecha '{fecha_examen}' "
                    "ya fue cargado. Se omite el proceso."
                )
                return False

    # ── Flujo normal: abrir formulario ───────────────────────────────────────
    btn_crear = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH,
             "//a[contains(@href,'/otrosAD/') and contains(@class,'btn-success')]")
        )
    )
    btn_crear.click()
    time.sleep(3)
    logger.debug("Formulario de ayuda diagnóstica abierto")
    return True


def _verificar_y_completar_diagnostico(driver, wait, codigo_diagnostico: str | None) -> None:
    """
    Verifica si el select2 de diagnóstico ya tiene una opción seleccionada.
    Si no tiene nada y se dispone de codigo_diagnostico, lo busca y selecciona.
    """
    try:

        # ✅ Verificar selección en el contenedor visual de Select2,
        # NO en el <select> oculto (que siempre está vacío visualmente)
        rendered_items = driver.find_elements(
            By.CSS_SELECTOR,
            ".select2-selection__rendered .select2-selection__choice"
        )

        if rendered_items:
            logger.debug(
                "✔ Diagnóstico ya seleccionado: '%s'",
                rendered_items[0].get_attribute(
                    "title") or rendered_items[0].text
            )
            return True

        if not codigo_diagnostico:
            logger.warning(
                "⚠ Diagnóstico vacío y no se dispone de codigo_diagnostico")
            return False

        logger.debug("Diagnóstico vacío. Buscando código: '%s'",
                     codigo_diagnostico)

        # ✅ Clic en el contenedor Select2 para abrirlo (más confiable que buscar el input directamente)
        select2_container = wait.until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#diagnostico + .select2-container .select2-selection"
            ))
        )
        select2_container.click()
        time.sleep(0.3)

        # ✅ Re-localizar el input DESPUÉS del clic para evitar stale reference
        search_input = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".select2-container--open .select2-search__field"
            ))
        )
        search_input.send_keys(codigo_diagnostico[:4])
        time.sleep(1.5)  # Esperar sugerencias del servidor

        # ✅ Esperar que aparezca el dropdown con resultados (no "Searching..." ni vacío)
        wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".select2-results__option:not(.select2-results__message)"
            ))
        )

        # ✅ Re-localizar el resultado justo antes de hacer clic (evita stale)
        resultado = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//li[contains(@class,'select2-results__option') and contains(., '{codigo_diagnostico}')]"
            ))
        )

        resultado_texto = resultado.text  # ✅ Leer el texto ANTES de hacer clic
        resultado.click()

        logger.debug("✔ Diagnóstico seleccionado: '%s'", resultado_texto)
        return True

    except StaleElementReferenceException:
        # ✅ Retry automático en caso de stale
        logger.warning("⚠ StaleElementReference detectado, reintentando...")
        time.sleep(1)
        return _verificar_y_completar_diagnostico(driver, wait, codigo_diagnostico)

    except Exception as e:
        logger.error("❌ Error al completar diagnóstico: %s", e)
        return False


def _completar_formulario(driver, wait, pdf: dict, sentinel_data: dict | None, sede: str | None, firmante: str | None) -> None:
    """
    Rellena todos los campos del formulario de carga de ayuda diagnóstica
    y lo envía.

    Args:
        pdf             : dict con claves examen, fecha_atencion, ruta.
        sentinel_data   : dict con datos del número Sentinel (puede ser None).
        codigo_diagnostico : código de diagnóstico extraído de la nota de enfermería (puede ser None).
        sede            : nombre de la sede a seleccionar (puede ser None).
        firmante        : nombre del firmante (puede ser None).
    """
    tipo_examen = pdf["examen"]
    fecha_atencion = pdf["fecha_atencion"]
    fecha_busqueda = fecha_solo_dia(fecha_atencion)   # DD/MM/YYYY
    date_examen = sentinel_a_input(fecha_atencion)  # YYYY-MM-DD para el input
    sentinel_numero = sentinel_data.get(
        "numero_sentinel") if sentinel_data else None
    codigo_diagnostico = sentinel_data.get(
        "codigo_diagnostico") if sentinel_data else None
    equipo = sentinel_data.get("equipo") if sentinel_data else None
    marca = sentinel_data.get("marca") if sentinel_data else None

    service = SERVICIOS_EXAMEN.get(tipo_examen, SERVICIO_DEFAULT)
    logger.debug("Servicio a seleccionar: '%s' | Fecha examen: %s",
                 service, date_examen)

    # seleccionar
    sede_selected = seleccionar_sede(driver, wait, sede)

    if not sede_selected:
        logger.warning(
            "⚠ No se pudo seleccionar la sede '%s'. Continuando sin seleccionar sede.", sede)

    # 1. Planilla de ingreso (servicio + fecha)
    if not buscar_opcion_select(driver, "planilla_ingreso", service, fecha_buscar=date_examen):
        logger.warning(
            "⚠ No se pudo seleccionar planilla_ingreso: '%s'", service)
        raise Exception(
            f"No se pudo seleccionar planilla_ingreso: '{service} con la fecha {date_examen}'")

    # 2. Fecha de elaboración
    fecha_input = wait.until(
        EC.presence_of_element_located((By.ID, "fecha_elaboracion"))
    )
    driver.execute_script(
        f"arguments[0].value = '{fecha_busqueda}';", fecha_input)
    logger.debug("Fecha de elaboración: %s", fecha_busqueda)

    # 3. Input de archivo (obtener referencia antes de los selects siguientes)
    input_file = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='file'][name='archivos[]']")
        )
    )

    # 4. Select de servicio
    if not buscar_opcion_select(driver, "select_servicio_id", service):
        logger.warning(
            "⚠ Primer intento fallido select_servicio_id. Reintentando...")
        if not buscar_opcion_select(driver, "select_servicio_id", service):
            logger.error(
                "❌ No se pudo seleccionar select_servicio_id: '%s'", service)

    # 5. Selects específicos por tipo de examen
    # if tipo_examen == "HOLTER":
    if not buscar_opcion_select(driver, "select_equipo_medico_id", equipo):
        logger.warning("⚠ No se pudo seleccionar equipo HOLTER")
        raise (Exception("No se pudo seleccionar equipo HOLTER"))

    # if tipo_examen == "MAPA":
    if not buscar_opcion_select(driver, "select_marca_equipo", marca):
        logger.warning("⚠ No se pudo seleccionar marca para examen MAPA")
        raise (Exception("No se pudo seleccionar marca para examen MAPA"))

    # 6. Código serial / número Sentinel
    # if sentinel_numero and tipo_examen in ("HOLTER"):
    if not buscar_opcion_select(driver, "select_codigo_serial", sentinel_numero):
        logger.warning(
            "⚠ No se pudo seleccionar número Sentinel: '%s'", sentinel_numero)
        raise (Exception(f"No se encontro el serial: '{sentinel_numero}'"))

    if firmante:
        firmante_limpio = _limpiar_nombre_firmante(firmante)
        firmante_limpio = _normalizar_nombre_busqueda(firmante_limpio)
        if not buscar_opcion_select_lectura(driver, "usuario_lectura", firmante_limpio):
            logger.warning(
                "⚠ No se pudo seleccionar firmante: '%s'", firmante_limpio)

    # 7. Adjuntar archivo
    input_file.send_keys(pdf["ruta"])
    logger.debug("Archivo adjuntado: %s", pdf["ruta"])

    # 8. Consentimiento informado
    input_radio = wait.until(
        EC.presence_of_element_located(
            (By.XPATH,
             "//input[@name='consentimiento_informado' and @value='1']")
        )
    )
    ins_si = driver.find_element(
        By.XPATH,
        "//input[@name='consentimiento_informado' and @value='1']/following-sibling::ins",
    )
    marcar_radio(driver, input_radio, ins_si)

    # 9. Diagnóstico (si aplica y no está prellenado)
    if not _verificar_y_completar_diagnostico(driver, wait, codigo_diagnostico):
        logger.warning(
            "⚠ No se pudo completar el diagnóstico para este examen.")
        raise Exception("No se pudo completar el diagnóstico")

    # 10. Guardar
    btn_guardar = driver.find_element(
        By.CSS_SELECTOR, "input[type='submit'].btn.green")
    btn_guardar.click()
    time.sleep(5)


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------

def subir_pdfs(driver, wait, pdfs: list[dict]) -> tuple[int, int]:
    """
    Itera la lista de PDFs descargados de Sentinel y sube cada uno a CEMDE
    completando el formulario de ayuda diagnóstica.

    Args:
        driver : instancia de Selenium WebDriver (ya autenticado en CEMDE).
        wait   : WebDriverWait asociado.
        pdfs   : lista de dicts producida por procesar_tabla_sentinel().

    Returns:
        Tupla (exitosos, fallidos).
    """
    exitosos = 0
    fallidos = 0
    rechazados = 0
    procesados = 0
    report = UploadReport()                                            # ← NUEVO

    for idx, pdf in enumerate(pdfs, start=1):
        cedula = pdf["cedula"]
        tipo_examen = pdf["examen"]
        fecha_atencion = pdf["fecha_atencion"]
        fecha_busqueda = fecha_solo_dia(fecha_atencion)
        estado = pdf.get("estado", "CONFIRMADO")
        firmante = pdf.get("firmante", None)

        logger.info("─" * 50)
        logger.info(
            "📤 Subiendo PDF %d/%d | %s | Cédula: %s | Examen: %s | Fecha: %s",
            idx, len(pdfs), pdf["nombre"], cedula, tipo_examen, fecha_atencion,
        )

        try:
            # 1. Abrir paciente
            abrir_paciente(driver, wait, cedula)

            # ── Flujo RECHAZADO ──────────────────────────────────────────
            if estado == "RECHAZADO":
                ok = agregar_nota_aclaratoria_rechazado(
                    driver, wait, fecha_busqueda, tipo_examen
                )
                if ok:
                    rechazados += 1
                    report.reject(pdf)
                    logger.info(
                        "✅ Nota aclaratoria agregada (%d/%d) | Cédula: %s | Examen: %s",
                        idx, len(pdfs), cedula, tipo_examen,
                    )
                else:
                    fallidos += 1
                    report.fail(pdf, Exception(
                        "El examen esta rechazado pero no se pudo agregar la nota aclaratoria"))
                    logger.warning(
                        "⚠ No se pudo agregar nota aclaratoria | Cédula: %s | Examen: %s",
                        cedula, tipo_examen,
                    )
                continue

            # ── Flujo CONFIRMADO / RECONFIRMADO ──────────────────────────
            # 2. Obtener sede
            sede = obtener_sede(driver, wait, fecha_busqueda)
            if not sede:
                logger.warning("⚠ No se pudo determinar la sede del paciente")

            # 3. Número Sentinel desde nota de enfermería (solo HOLTER / MAPA)
            sentinel_data = obtener_numero_sentinel(
                driver, wait, fecha_busqueda, tipo_examen
            )

            # sentinel_numero = sentinel_data["numero_sentinel"] if sentinel_data else None
            # codigo_diagnostico = sentinel_data["codigo_diagnostico"] if sentinel_data else None

            # 4. Navegar al formulario y completarlo
            if not _abrir_formulario_otros_ad(driver, wait, fecha_busqueda, tipo_examen):
                logger.info("⏭ Omitiendo carga de PDF para este examen.")
                procesados += 1
                report.already(pdf)                                       # ← NUEVO
                continue

            _completar_formulario(
                driver, wait, pdf, sentinel_data, sede, firmante)

            exitosos += 1
            report.ok(pdf)                                            # ← NUEVO
            logger.info(
                "✅ PDF subido correctamente (%d/%d) | Cédula: %s | Examen: %s",
                idx, len(pdfs), cedula, tipo_examen,
            )

        except Exception as e:
            fallidos += 1
            report.fail(pdf, e)                                       # ← NUEVO
            logger.error(
                "❌ Error subiendo PDF %d/%d | Cédula: %s | Archivo: %s | Error: %s",
                idx, len(pdfs), cedula, pdf["nombre"], e,
                exc_info=True,
            )

    # ── Guardar reporte al finalizar ─────────────────────────────────────── NUEVO
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_reporte = os.path.join("logs", f"reporte_{timestamp}.txt")
    report.guardar(ruta_reporte)
    logger.info("📋 Reporte guardado en: %s", ruta_reporte)
    # ─────────────────────────────────────────────────────────────────────────

    return exitosos, fallidos, rechazados, procesados
