import logging

import requests
import os
import time
import re
from datetime import datetime
from openpyxl import load_workbook

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from selenium.webdriver.common.action_chains import ActionChains
from dotenv import load_dotenv
load_dotenv()


# =========================
# CONFIGURACIÓN
# =========================

DOWNLOAD_DIR = os.path.abspath("pdfs_descargados")

URL_LOGIN_SENTINEL = os.getenv(
    "URL_LOGIN_SENTINEL", "https://sentinel.sunu.be/Account/Login")
USUARIO_SENTINEL = os.getenv("USUARIO_SENTINEL")
PASSWORD_SENTINEL = os.getenv("PASSWORD_SENTINEL")

URL_LOGIN_CEMDE = os.getenv("URL_LOGIN_CEMDE")
EMAIL_CEMDE = os.getenv("EMAIL_CEMDE")
PASSWORD_CEMDE = os.getenv("PASSWORD_CEMDE")
URL_PACIENTES = os.getenv("URL_PACIENTES")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAPEO_TIPOS_EXAMEN = {
    'ecg ambulatorio': 'HOLTER',
    'mapa': 'MAPA',
    'ecg 12 derivaciones': 'ELECTROCARDIOGRAMA'
}

SERVICIOS_EXAMEN = {
    "HOLTER": "MONITOREO ELECTROCARDIOGRAFICO CONTINUO (HOLTER)",
    "MAPA": "MONITOREO AMBULATORIO DE PRESIÓN ARTERIAL SISTEMICA"
}

CEDULAS_PRUEBA = {
    # "52148335",
    "39170583",
    # "32348634",
    # "52148335"
}

cedulas_encontradas = set()


# =========================
# CONFIGURACIÓN LOGGING
# =========================

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(
    LOG_DIR, f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# =========================
# UTILIDADES
# =========================

def buscar_opcion_select(driver, select_id, texto_buscar, fecha_buscar=None, timeout=10):
    logger.debug("Buscando opción en select2 '%s': '%s' (fecha: %s)",
                 select_id, texto_buscar, fecha_buscar or "N/A")
    try:
        trigger = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 f"[aria-labelledby='select2-{select_id}-container']")
            )
        )
        trigger.click()

        opciones = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, ".select2-results__option")
            )
        )

        palabras = texto_buscar.lower().split()
        logger.debug("Revisando %d opciones en select2 '%s'",
                     len(opciones), select_id)

        for opcion in opciones:
            texto = opcion.text.strip()
            if texto.lower().startswith("seleccione"):
                continue

            texto_lower = texto.lower()
            if all(p in texto_lower for p in palabras):
                if fecha_buscar and fecha_buscar not in texto:
                    continue
                opcion.click()
                logger.info("✅ Opción seleccionada en '%s': %s",
                            select_id, texto)
                return True

        logger.warning(
            "⚠ Opción no encontrada en select2 '%s' | Buscado: '%s' | Fecha: '%s'",
            select_id, texto_buscar, fecha_buscar or "N/A"
        )
        return False

    except Exception as e:
        logger.error("❌ Error en select2 '%s': %s",
                     select_id, e, exc_info=True)
        return False


# =========================
# CONFIGURAR EDGE
# =========================

edge_options = Options()
edge_options.add_argument("--start-maximized")

prefs = {
    "download.prompt_for_download": False,
    "plugins.always_open_pdf_externally": True,
    "download.default_directory": DOWNLOAD_DIR
}

edge_options.add_experimental_option("prefs", prefs)

driver = webdriver.Edge(service=Service(), options=edge_options)
wait = WebDriverWait(driver, 25)


# =========================
# DESCARGAR PDF DESDE IFRAME
# =========================

def descargar_pdf_desde_iframe(driver, ruta_pdf):
    logger.debug("Intentando descargar PDF desde iframe → %s", ruta_pdf)
    try:
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//iframe[contains(@src,'GetPdf')]")
            )
        )

        pdf_url = iframe.get_attribute("src")

        if not pdf_url.startswith("http"):
            pdf_url = "http://181.143.85.123" + pdf_url

        logger.debug("URL del PDF: %s", pdf_url)

        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        response = session.get(pdf_url, verify=False, timeout=30)

        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and "pdf" in content_type:
            with open(ruta_pdf, "wb") as f:
                f.write(response.content)
            logger.info("✅ PDF guardado: %s (%.1f KB)", os.path.basename(
                ruta_pdf), len(response.content) / 1024)
            return True
        else:
            logger.warning(
                "⚠ Respuesta inesperada al descargar PDF | Status: %d | Content-Type: %s",
                response.status_code, content_type
            )

    except Exception as e:
        logger.error("❌ No se pudo descargar PDF desde iframe: %s",
                     e, exc_info=True)

    return False


# =========================
# LOGIN SENTINEL
# =========================

logger.info("=" * 60)
logger.info("🔵 INICIANDO SESIÓN EN SENTINEL")
logger.info("=" * 60)

driver.get(URL_LOGIN_SENTINEL)

wait.until(EC.presence_of_element_located(
    (By.ID, "Staff_Username"))).send_keys(USUARIO_SENTINEL)
driver.find_element(By.ID, "Staff_Password").send_keys(
    PASSWORD_SENTINEL + Keys.ENTER)
wait.until(EC.presence_of_element_located((By.ID, "Button_Tests")))

logger.info("✅ Login Sentinel exitoso | Usuario: %s", USUARIO_SENTINEL)

wait.until(EC.element_to_be_clickable((By.ID, "Button_Tests"))).click()
time.sleep(3)

logger.info("📋 Accediendo a listado de pruebas")


# =========================
# RECORRER TABLA PAGINADA
# =========================

def procesar_tabla_sentinel():
    pdfs_descargados = []
    pagina = 1
    total_filas_procesadas = 0
    total_filas_omitidas = 0

    while True:
        logger.info("─" * 50)
        logger.info("📄 Procesando página %d", pagina)

        wait.until(EC.presence_of_element_located((By.XPATH, "//rows/row")))
        rows = driver.find_elements(By.XPATH, "//rows/row")

        logger.info("Filas encontradas en página %d: %d", pagina, len(rows))

        for i in range(len(rows)):
            try:
                rows = driver.find_elements(By.XPATH, "//rows/row")
                row = rows[i]
                cells = row.find_elements(By.XPATH, "./cell")

                if len(cells) < 12:
                    logger.debug(
                        "Fila %d omitida: menos de 12 celdas (%d)", i, len(cells))
                    total_filas_omitidas += 1
                    continue

                cedula = cells[8].text.strip().rstrip('.')
                nombre = cells[9].text.strip()
                fecha_atencion = cells[11].text.strip()

                logger.debug("Revisando fila %d | %s | %s | %s",
                             i, cedula, nombre, fecha_atencion)

                if cedula not in CEDULAS_PRUEBA:
                    total_filas_omitidas += 1
                    continue

                logger.info("🎯 Cédula de prueba encontrada: %s | %s | %s",
                            cedula, nombre, fecha_atencion)
                cedulas_encontradas.add(cedula)

                if cedulas_encontradas == CEDULAS_PRUEBA:
                    logger.info("✅ Todas las cédulas de prueba encontradas (%d/%d)",
                                len(cedulas_encontradas), len(CEDULAS_PRUEBA))
                    return pdfs_descargados

                examen_cell = cells[18]
                examen_raw = examen_cell.get_attribute("tooltip")

                if examen_raw:
                    examen_raw = examen_raw.strip()
                    examen = MAPEO_TIPOS_EXAMEN.get(
                        examen_raw.lower().strip(), "")
                    logger.debug("Tipo examen | Raw: '%s' → Mapeado: '%s'",
                                 examen_raw, examen or "(sin mapeo)")
                else:
                    examen = ""
                    logger.debug("Tipo examen: sin tooltip en celda 18")

                estado = None
                for cell in cells:
                    texto = cell.text.strip().upper()
                    if texto in ["CONFIRMADO", "RECONFIRMADO"]:
                        estado = texto
                        break

                logger.info(
                    "Fila | Nombre: %s | Cédula: %s | Examen: %s | Fecha: %s | Estado: %s",
                    nombre, cedula, examen or "(vacío)", fecha_atencion, estado or "(sin estado)"
                )

                if estado not in ["CONFIRMADO", "RECONFIRMADO"]:
                    logger.info(
                        "⏭ Fila omitida: estado '%s' no es CONFIRMADO ni RECONFIRMADO", estado)
                    total_filas_omitidas += 1
                    continue

                total_filas_procesadas += 1
                row.click()

                wait.until(EC.element_to_be_clickable(
                    (By.ID, "Button_EditReport"))).click()

                try:
                    wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(.,'Aceptar')]"))).click()
                    logger.debug("Diálogo de confirmación aceptado")
                except:
                    logger.debug("Sin diálogo de confirmación")

                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(),'Revisar informe')]")))

                time.sleep(2)

                # Obtener médico firmante
                firmante = None
                filas_firmas = driver.find_elements(
                    By.XPATH, "//editlist[@id='Report_SignaturesTable']//rows/row")

                logger.debug("Revisando %d filas de firmas", len(filas_firmas))

                for fila in filas_firmas:
                    celdas = fila.find_elements(By.XPATH, "./cell")
                    if len(celdas) < 5:
                        continue
                    decision = celdas[4].text.strip().lower()
                    if decision in ["confirmado", "reconfirmado"]:
                        firmante = celdas[1].text.strip()
                        logger.info("✅ Firmante: %s (decisión: %s)",
                                    firmante, decision)
                        break

                if not firmante:
                    logger.warning(
                        "⚠ No se encontró firmante confirmado para %s | %s", nombre, cedula)

                nombre_archivo = f"{cedula}_{nombre}".replace(
                    " ", "_") + ".pdf"
                carpeta_medico = firmante.replace(
                    " ", "_") if firmante else "SIN_FIRMANTE"
                carpeta_destino = os.path.join(DOWNLOAD_DIR, carpeta_medico)
                os.makedirs(carpeta_destino, exist_ok=True)

                ruta_pdf = os.path.join(carpeta_destino, nombre_archivo)

                descargado = descargar_pdf_desde_iframe(driver, ruta_pdf)
                if not descargado:
                    logger.warning(
                        "⚠ PDF no descargado para %s | %s", nombre, cedula)

                pdfs_descargados.append({
                    "ruta": ruta_pdf,
                    "nombre": nombre_archivo,
                    "cedula": cedula,
                    "examen": examen,
                    "fecha_atencion": fecha_atencion
                })

                driver.back()
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//rows/row")))
                # ✅ Pausa adicional para PCs lentos (la tabla puede seguir cargando filas)
                wait.until(lambda d: len(
                    d.find_elements(By.XPATH, "//rows/row")) > i)

            except Exception as e:
                logger.error(
                    "❌ Error procesando fila %d en página %d: %s", i, pagina, e, exc_info=True)

        logger.info(
            "Página %d completada | Procesadas: %d | Omitidas: %d | PDFs acumulados: %d",
            pagina, total_filas_procesadas, total_filas_omitidas, len(
                pdfs_descargados)
        )

        try:
            next_button = driver.find_element(By.CSS_SELECTOR, "span.nextPage")
            if "disabled" in next_button.get_attribute("class"):
                logger.info("📄 Última página alcanzada")
                break
            logger.info("➡ Avanzando a página %d", pagina + 1)
            driver.execute_script("arguments[0].click();", next_button)
            pagina += 1
            time.sleep(3)
        except Exception as e:
            logger.warning("⚠ No se pudo avanzar de página: %s", e)
            break

    logger.info("=" * 60)
    logger.info("📊 RESUMEN SENTINEL | Páginas: %d | PDFs descargados: %d | Cédulas halladas: %d/%d",
                pagina, len(pdfs_descargados), len(cedulas_encontradas), len(CEDULAS_PRUEBA))
    logger.info("=" * 60)
    return pdfs_descargados


pdfs_descargados = procesar_tabla_sentinel()

logger.info("PDFs listos para subir: %d", len(pdfs_descargados))


# =========================
# LOGIN CEMDE
# =========================

logger.info("=" * 60)
logger.info("🟢 INICIANDO SESIÓN EN CEMDE")
logger.info("=" * 60)

driver.get(URL_LOGIN_CEMDE)

wait.until(EC.presence_of_element_located(
    (By.NAME, "email"))).send_keys(EMAIL_CEMDE)
driver.find_element(By.NAME, "password").send_keys(PASSWORD_CEMDE)
driver.find_element(By.XPATH, "//button[@type='submit']").click()

time.sleep(5)

logger.info("✅ Login CEMDE exitoso | Usuario: %s", EMAIL_CEMDE)


# =========================
# SUBIR PDFs
# =========================

pdfs_exitosos = 0
pdfs_fallidos = 0

for idx, pdf in enumerate(pdfs_descargados, start=1):
    logger.info("─" * 50)
    logger.info(
        "📤 Subiendo PDF %d/%d | Archivo: %s | Cédula: %s | Examen: %s | Fecha: %s",
        idx, len(pdfs_descargados),
        pdf['nombre'], pdf['cedula'], pdf['examen'], pdf['fecha_atencion']
    )

    cedula = pdf["cedula"]
    tipo_examen = pdf["examen"]
    fecha_atencion = pdf["fecha_atencion"]
    sentinel_numero = None

    try:
        driver.get(URL_PACIENTES)
        time.sleep(3)

        input_busqueda = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='search']")
        ))
        input_busqueda.clear()
        input_busqueda.send_keys(cedula)

        resultado = wait.until(EC.element_to_be_clickable(
            (By.XPATH,
             f"//ul[@id='lista-pacientes']//a[contains(@class,'list-group-item') and contains(.,'{cedula}')]")
        ))
        driver.execute_script("arguments[0].click();", resultado)
        logger.debug("Paciente encontrado y abierto: %s", cedula)

        # =====================
        # Obtener Sede
        # =====================

        tab_atenciones = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-citas']")
        ))
        tab_atenciones.click()
        time.sleep(2)

        filas = driver.find_elements(
            By.XPATH, "//table[@id='pacientes-table']//tbody/tr"
        )

        sede = None
        fecha_busqueda = fecha_atencion.split(" ")[0]

        for fila in filas:
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) < 3:
                continue
            fecha_tabla = celdas[1].text.strip()
            logger.debug("Comparando fechas: '%s' con '%s'",
                         fecha_busqueda, fecha_tabla)
            if fecha_busqueda in fecha_tabla:
                sede = celdas[2].text.strip()
                logger.info("🏥 Sede encontrada: %s", sede)
                break

        if not sede:
            logger.warning(
                "⚠ No se encontró sede para cédula %s en fecha %s", cedula, fecha_busqueda)

        # =====================
        # NOTAS DE ENFERMERÍA (solo HOLTER / MAPA)
        # =====================

        if tipo_examen in ["HOLTER", "MAPA"]:
            logger.debug(
                "Buscando nota de enfermería para examen tipo %s", tipo_examen)

            tab_notas = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@href='#tab-notas-enfermeria']")
            ))
            tab_notas.click()

            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//table[@id='table']//tbody/tr")
            ))

            filas_notas = driver.find_elements(
                By.XPATH, "//table[@id='table']//tbody/tr"
            )
            logger.debug("Filas de notas encontradas: %d", len(filas_notas))

            nota_encontrada = False

            for fila in filas_notas:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) < 3:
                    continue

                fecha_tabla = celdas[0].text.strip()
                logger.debug("Comparando fecha nota: '%s' con '%s'",
                             fecha_busqueda, fecha_tabla)

                if fecha_busqueda != fecha_tabla:
                    continue

                boton_ver = fila.find_element(
                    By.XPATH, ".//a[contains(@href,'notasEnfermerias')]"
                )

                # ✅ FIX 1: Capturar handles ANTES de abrir la nueva pestaña
                ventana_principal = driver.current_window_handle
                handles_antes = set(driver.window_handles)

                driver.execute_script("arguments[0].click();", boton_ver)
                logger.info(
                    "📝 Nota de enfermería abierta para fecha %s", fecha_busqueda)

                # ✅ FIX 2: Esperar y cambiar SOLO a la pestaña recién abierta
                wait.until(lambda d: set(d.window_handles) - handles_antes)
                nueva_ventana = (set(driver.window_handles) -
                                 handles_antes).pop()
                driver.switch_to.window(nueva_ventana)
                logger.debug("Cambiado a nueva ventana: %s", nueva_ventana)

                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//table[contains(@class,'table-condensed')]")
                ))

                # Extraer servicio
                servicio = driver.find_element(
                    By.XPATH,
                    "//td[contains(text(),'Servicio')]/following-sibling::td//input"
                ).get_attribute("value").strip()

                logger.info(
                    "Servicio en nota: '%s' | Examen Sentinel: '%s'", servicio, tipo_examen)

                # Validar servicio vs examen
                palabras_examen = SERVICIOS_EXAMEN.get(tipo_examen.upper(), [])
                servicio_upper = servicio.upper()
                coincide = any(
                    palabra in servicio_upper for palabra in palabras_examen)

                # ✅ FIX 3: Cerrar pestaña siempre, coincida o no
                # driver.close()
                # driver.switch_to.window(ventana_principal)
                # logger.debug("Pestaña cerrada. Regresado a ventana principal")

                if not coincide:
                    logger.warning(
                        "⚠ Servicio NO coincide con examen, buscando siguiente nota | Servicio: '%s' | Examen: '%s'",
                        servicio, tipo_examen
                    )
                    logger.debug(
                        "Pestaña cerrada. Regresado a ventana principal")
                    driver.close()                                    # ← cierra solo si no coincide
                    driver.switch_to.window(ventana_principal)
                    continue

                # Solo llega aquí si coincide
                logger.info(
                    "✅ Servicio coincide con examen | Servicio: '%s' | Examen: '%s'", servicio, tipo_examen)

                # Extraer observaciones y número Sentinel
                observaciones = driver.find_element(
                    By.CLASS_NAME, "observaciones_nota_enfermeria"
                ).text

                match = re.search(r"SENTINEL\s*#\s*(\d+)",
                                  observaciones, re.IGNORECASE)
                if match:
                    sentinel_numero = match.group(1)
                    logger.info("🔢 Número Sentinel extraído: %s",
                                sentinel_numero)
                else:
                    logger.warning(
                        "⚠ No se encontró número Sentinel en observaciones de cédula %s", cedula
                    )

                # ← cierra después de extraer todo
                driver.close()
                driver.switch_to.window(ventana_principal)
                logger.debug("Pestaña cerrada. Regresado a ventana principal")

                nota_encontrada = True
                break

            if not nota_encontrada:
                logger.warning(
                    "⚠ No se encontró nota de enfermería válida para cédula %s en fecha %s",
                    cedula, fecha_busqueda
                )

        # =====================
        # IR A AYUDAS DIAGNOSTICAS
        # =====================

        tab_ayudas = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-ayudas-diagnosticas']")))
        tab_ayudas.click()
        time.sleep(2)

        tab_otros = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='#tab-otros-ad']")))
        tab_otros.click()
        time.sleep(2)

        btn_crear = wait.until(EC.element_to_be_clickable(
            (By.XPATH,
             "//a[contains(@href,'/otrosAD/') and contains(@class,'btn-success')]")
        ))
        btn_crear.click()
        time.sleep(3)
        logger.debug("Formulario de ayuda diagnóstica abierto")

        # =====================
        # FORMULARIO DE SUBIDA
        # =====================

        service = SERVICIOS_EXAMEN.get(
            tipo_examen, "ELECTROCARDIOGRAMA DE RITMO O DE SUPERFICIE SOD")
        date_examen = datetime.strptime(
            fecha_atencion, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d")

        logger.debug(
            "Servicio a seleccionar: '%s' | Fecha examen: %s", service, date_examen)

        if not buscar_opcion_select(driver, "planilla_ingreso", service, fecha_buscar=date_examen):
            logger.warning(
                "⚠ No se pudo seleccionar planilla_ingreso: '%s'", service)

        fecha_input = wait.until(
            EC.presence_of_element_located((By.ID, "fecha_elaboracion")))
        driver.execute_script(
            f"arguments[0].value = '{fecha_busqueda}';", fecha_input)
        logger.debug("Fecha de elaboración establecida: %s", fecha_busqueda)

        input_file = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='file'][name='archivos[]']")
        ))

        if not buscar_opcion_select(driver, "select_servicio_id", service):
            logger.warning(
                "⚠ Primer intento fallido para select_servicio_id: '%s'. Reintentando...", service)
            if not buscar_opcion_select(driver, "select_servicio_id", service):
                logger.error(
                    "❌ No se pudo seleccionar select_servicio_id tras 2 intentos: '%s'", service)

        if tipo_examen == "HOLTER":
            if not buscar_opcion_select(driver, "select_equipo_medico_id", "HOLTER"):
                logger.warning("⚠ No se pudo seleccionar equipo HOLTER")
                continue

        if tipo_examen == "MAPA":
            if not buscar_opcion_select(driver, "select_marca_equipo", " SPACELABS HEALTHCARE"):
                logger.warning(
                    "⚠ No se pudo seleccionar marca para examen MAPA")
                continue

        if sentinel_numero:
            if not buscar_opcion_select(driver, "select_codigo_serial", sentinel_numero):
                logger.warning(
                    "⚠ No se pudo seleccionar número Sentinel: '%s'", sentinel_numero)
                continue

        input_file.send_keys(pdf["ruta"])
        logger.debug("Archivo adjuntado: %s", pdf["ruta"])

        # radio_si = driver.find_element(
        #     By.XPATH, "//input[@name='consentimiento_informado' and @value='1']"
        # )
        # driver.execute_script("arguments[0].click();", radio_si)
        # logger.debug("Consentimiento informado marcado como Sí")

        ins_si = wait.until(EC.presence_of_element_located(
            (By.XPATH,
             "//input[@name='consentimiento_informado' and @value='1']/following-sibling::ins")
        ))
        driver.execute_script("arguments[0].scrollIntoView(true);", ins_si)
        time.sleep(0.3)

        input_radio = driver.find_element(
            By.XPATH, "//input[@name='consentimiento_informado' and @value='1']"
        )

        # ✅ Estrategia 1: clic directo en el ins
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(ins_si))

            # Click REAL (no JS)
            ins_si.click()

            # Esperar que el radio esté marcado (validación real)
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script(
                    "return arguments[0].checked;", input_radio)
            )

        except Exception:
            pass

        # Verificar
        marcado = driver.execute_script(
            "return arguments[0].checked;", input_radio)

        if not marcado:
            # ✅ Estrategia 2: forzar checked + disparar eventos que iCheck escucha
            driver.execute_script("""
                var input = arguments[0];
                input.checked = true;
                input.dispatchEvent(new Event('ifChecked', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('click', { bubbles: true }));
            """, input_radio)
            marcado = driver.execute_script(
                "return arguments[0].checked;", input_radio)

        if not marcado:
            # ✅ Estrategia 3: ActionChains sobre el ins
            ActionChains(driver).move_to_element(ins_si).click().perform()
            time.sleep(0.3)
            marcado = driver.execute_script(
                "return arguments[0].checked;", input_radio)

        if marcado:
            logger.info("✅ Consentimiento informado marcado como Sí")
        else:
            logger.error("❌ No se pudo marcar el consentimiento informado")

        btn_guardar = driver.find_element(
            By.CSS_SELECTOR, "input[type='submit'].btn.green")
        btn_guardar.click()
        time.sleep(5)

        pdfs_exitosos += 1
        logger.info("✅ PDF subido correctamente (%d/%d) | Cédula: %s | Examen: %s",
                    idx, len(pdfs_descargados), cedula, tipo_examen)

    except Exception as e:
        pdfs_fallidos += 1
        logger.error(
            "❌ Error subiendo PDF %d/%d | Cédula: %s | Archivo: %s | Error: %s",
            idx, len(pdfs_descargados), cedula, pdf['nombre'], e,
            exc_info=True
        )


# =========================
# RESUMEN FINAL
# =========================

logger.info("=" * 60)
logger.info("🎉 PROCESO COMPLETADO")
logger.info("   PDFs procesados : %d", len(pdfs_descargados))
logger.info("   ✅ Exitosos      : %d", pdfs_exitosos)
logger.info("   ❌ Fallidos      : %d", pdfs_fallidos)
logger.info("   📁 Directorio   : %s", DOWNLOAD_DIR)
logger.info("   📄 Log guardado : %s", log_file)
logger.info("=" * 60)

driver.quit()
