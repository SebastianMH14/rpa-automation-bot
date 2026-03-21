import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from config.settings import SERVICIOS_EXAMEN, SERVICIO_DEFAULT
from modules.cemde.paciente import abrir_paciente, obtener_sede
from modules.cemde.notas_enfermeria import obtener_numero_sentinel
from utils.select2 import buscar_opcion_select
from utils.fecha import fecha_solo_dia, sentinel_a_input
from utils.radio import marcar_radio

logger = logging.getLogger("bot")


def _abrir_formulario_otros_ad(driver, wait) -> None:
    """Navega a la pestaña de ayudas diagnósticas → otros AD y abre el formulario."""
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

    btn_crear = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH,
             "//a[contains(@href,'/otrosAD/') and contains(@class,'btn-success')]")
        )
    )
    btn_crear.click()
    time.sleep(3)
    logger.debug("Formulario de ayuda diagnóstica abierto")


def _completar_formulario(driver, wait, pdf: dict, sentinel_numero: str | None) -> None:
    """
    Rellena todos los campos del formulario de carga de ayuda diagnóstica
    y lo envía.

    Args:
        pdf             : dict con claves examen, fecha_atencion, ruta.
        sentinel_numero : número Sentinel extraído de la nota de enfermería (puede ser None).
    """
    tipo_examen = pdf["examen"]
    fecha_atencion = pdf["fecha_atencion"]
    fecha_busqueda = fecha_solo_dia(fecha_atencion)   # DD/MM/YYYY
    date_examen = sentinel_a_input(fecha_atencion)  # YYYY-MM-DD para el input

    service = SERVICIOS_EXAMEN.get(tipo_examen, SERVICIO_DEFAULT)
    logger.debug("Servicio a seleccionar: '%s' | Fecha examen: %s",
                 service, date_examen)

    # 1. Planilla de ingreso (servicio + fecha)
    if not buscar_opcion_select(driver, "planilla_ingreso", service, fecha_buscar=date_examen):
        logger.warning(
            "⚠ No se pudo seleccionar planilla_ingreso: '%s'", service)

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
    if tipo_examen == "HOLTER":
        if not buscar_opcion_select(driver, "select_equipo_medico_id", "HOLTER"):
            logger.warning("⚠ No se pudo seleccionar equipo HOLTER")
            return

    if tipo_examen == "MAPA":
        if not buscar_opcion_select(driver, "select_marca_equipo", "SPACELABS HEALTHCARE"):
            logger.warning("⚠ No se pudo seleccionar marca para examen MAPA")
            return

    # 6. Código serial / número Sentinel
    if sentinel_numero:
        if not buscar_opcion_select(driver, "select_codigo_serial", sentinel_numero):
            logger.warning(
                "⚠ No se pudo seleccionar número Sentinel: '%s'", sentinel_numero)
            return

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


    # 9. Guardar
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

    for idx, pdf in enumerate(pdfs, start=1):
        cedula = pdf["cedula"]
        tipo_examen = pdf["examen"]
        fecha_atencion = pdf["fecha_atencion"]
        fecha_busqueda = fecha_solo_dia(fecha_atencion)

        logger.info("─" * 50)
        logger.info(
            "📤 Subiendo PDF %d/%d | %s | Cédula: %s | Examen: %s | Fecha: %s",
            idx, len(pdfs), pdf["nombre"], cedula, tipo_examen, fecha_atencion,
        )

        try:
            # 1. Abrir paciente
            abrir_paciente(driver, wait, cedula)

            # 2. Obtener sede (informativo, puede usarse para validaciones futuras)
            obtener_sede(driver, wait, fecha_busqueda)

            # 3. Número Sentinel desde nota de enfermería (solo HOLTER / MAPA)
            sentinel_numero = obtener_numero_sentinel(
                driver, wait, fecha_busqueda, tipo_examen
            )

            # 4. Navegar al formulario y completarlo
            _abrir_formulario_otros_ad(driver, wait)
            _completar_formulario(driver, wait, pdf, sentinel_numero)

            exitosos += 1
            logger.info(
                "✅ PDF subido correctamente (%d/%d) | Cédula: %s | Examen: %s",
                idx, len(pdfs), cedula, tipo_examen,
            )

        except Exception as e:
            fallidos += 1
            logger.error(
                "❌ Error subiendo PDF %d/%d | Cédula: %s | Archivo: %s | Error: %s",
                idx, len(pdfs), cedula, pdf["nombre"], e,
                exc_info=True,
            )

    return exitosos, fallidos
