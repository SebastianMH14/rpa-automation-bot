import os
from dotenv import load_dotenv

load_dotenv()

# ================================
# DIRECTORIOS
# ================================
DOWNLOAD_DIR = os.path.abspath("pdfs_descargados")
LOG_DIR = os.path.abspath("logs")

# ================================
# SENTINEL
# ================================
URL_LOGIN_SENTINEL = os.getenv("URL_LOGIN_SENTINEL", "https://sentinel.sunu.be/Account/Login")
USUARIO_SENTINEL   = os.getenv("USUARIO_SENTINEL")
PASSWORD_SENTINEL  = os.getenv("PASSWORD_SENTINEL")

# ================================
# CEMDE
# ================================
URL_LOGIN_CEMDE = os.getenv("URL_LOGIN_CEMDE")
EMAIL_CEMDE     = os.getenv("EMAIL_CEMDE")
PASSWORD_CEMDE  = os.getenv("PASSWORD_CEMDE")
URL_PACIENTES   = os.getenv("URL_PACIENTES")

# ================================
# MAPEOS DE NEGOCIO
# ================================
MAPEO_TIPOS_EXAMEN = {
    "ecg ambulatorio"   : "HOLTER",
    "mapa"              : "MAPA",
    "ecg 12 derivaciones": "ELECTROCARDIOGRAMA",
}

SERVICIOS_EXAMEN = {
    "HOLTER": "MONITOREO ELECTROCARDIOGRAFICO CONTINUO (HOLTER)",
    "MAPA"  : "MONITOREO AMBULATORIO DE PRESIÓN ARTERIAL SISTEMICA",
    # ELECTROCARDIOGRAMA no tiene servicio especial → usa el default del formulario
}

SERVICIO_DEFAULT = "ELECTROCARDIOGRAMA DE RITMO O DE SUPERFICIE SOD"

# ================================
# CÉDULAS EN MODO PRUEBA
# ================================
# En producción deja este set vacío → el bot procesará TODAS las filas.
# En desarrollo pon las cédulas que quieres probar.
CEDULAS_PRUEBA: set[str] = {
    # "39170583",
}