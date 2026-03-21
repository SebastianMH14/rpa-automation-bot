# Bot Sentinel → CEMDE

Automatización que descarga informes confirmados desde **Sentinel** y los sube al sistema **CEMDE** como ayudas diagnósticas, asociándolos al paciente, fecha y tipo de examen correcto.

---

## Flujo general

```
Sentinel (login) → Tabla paginada → Filtrar confirmados → Descargar PDFs
       ↓
CEMDE (login) → Buscar paciente → Nota de enfermería → Formulario ayuda diagnóstica
```

---

## Requisitos

- Python 3.11+
- Microsoft Edge instalado
- [Edge WebDriver](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/) en el PATH y compatible con la versión de Edge instalada

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd bot_sentinel_cemde

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / Mac
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales reales
```

---

## Configuración

Todas las variables de entorno van en el archivo `.env` (nunca se sube al repositorio):

| Variable | Descripción |
|---|---|
| `URL_LOGIN_SENTINEL` | URL del login de Sentinel |
| `USUARIO_SENTINEL` | Usuario de Sentinel |
| `PASSWORD_SENTINEL` | Contraseña de Sentinel |
| `URL_LOGIN_CEMDE` | URL del login de CEMDE |
| `EMAIL_CEMDE` | Email de CEMDE |
| `PASSWORD_CEMDE` | Contraseña de CEMDE |
| `URL_PACIENTES` | URL de la lista de pacientes en CEMDE |

Los mapeos de negocio (tipos de examen, servicios, etc.) se configuran directamente en `config/settings.py`.

---

## Modo prueba vs producción

En `config/settings.py` existe el set `CEDULAS_PRUEBA`:

```python
# Modo prueba: solo procesa estas cédulas y se detiene al encontrarlas todas
CEDULAS_PRUEBA: set[str] = {
    "39170583",
}

# Modo producción: dejar vacío → procesa TODAS las filas de la tabla
CEDULAS_PRUEBA: set[str] = set()
```

---

## Uso

```bash
python main.py
```

El bot abre Edge de forma visible, ejecuta el flujo completo y cierra el navegador al terminar.

**Salida esperada en consola:**

```
2024-03-15 08:00:01 | INFO     | 📄 Log iniciado: logs/bot_log_20240315_080001.txt
2024-03-15 08:00:02 | INFO     | 🔵 INICIANDO SESIÓN EN SENTINEL
2024-03-15 08:00:08 | INFO     | ✅ Login Sentinel exitoso | Usuario: usuario@ejemplo.com
2024-03-15 08:00:11 | INFO     | 📄 Procesando página 1
...
2024-03-15 08:05:30 | INFO     | 🎉 PROCESO COMPLETADO
2024-03-15 08:05:30 | INFO     |    PDFs procesados : 5
2024-03-15 08:05:30 | INFO     |    ✅ Exitosos      : 5
2024-03-15 08:05:30 | INFO     |    ❌ Fallidos      : 0
```

---

## Estructura del proyecto

```
bot_sentinel_cemde/
│
├── main.py                          # Punto de entrada
├── requirements.txt
├── .env                             # Credenciales (NO subir al repo)
├── .env.example                     # Plantilla de variables de entorno
├── .gitignore
│
├── config/
│   └── settings.py                  # Variables de entorno + mapeos de negocio
│
├── core/
│   ├── driver.py                    # Configuración de Edge/Selenium
│   └── logger.py                    # Logger con salida a archivo y consola
│
├── modules/
│   ├── sentinel/
│   │   ├── login.py                 # Login en Sentinel
│   │   ├── tabla.py                 # Paginación, filtrado y descarga
│   │   └── pdf_downloader.py        # Descarga de PDF desde iframe
│   │
│   └── cemde/
│       ├── login.py                 # Login en CEMDE
│       ├── paciente.py              # Búsqueda de paciente y sede
│       ├── notas_enfermeria.py      # Extracción del número Sentinel
│       └── ayudas_diagnosticas.py  # Formulario de carga del PDF
│
├── utils/
│   ├── select2.py                   # Helper para desplegables Select2
│   ├── fecha.py                     # Conversión y parseo de fechas
│   └── radio.py                     # Marcado de radio buttons con iCheck
│
├── logs/                            # Generado automáticamente
└── pdfs_descargados/                # Generado automáticamente
    └── NOMBRE_MEDICO/
        └── CEDULA_NOMBRE_PACIENTE.pdf
```

---

## Logs

Cada ejecución genera un archivo en `logs/` con el nombre `bot_log_YYYYMMDD_HHMMSS.txt`.

- La **consola** muestra nivel `INFO` (mensajes relevantes del flujo).
- El **archivo** guarda nivel `DEBUG` (detalle completo para diagnóstico de errores).

---

## PDFs descargados

Los archivos se organizan automáticamente por médico firmante:

```
pdfs_descargados/
├── DR_JUAN_PEREZ/
│   ├── 39170583_MARIA_GARCIA.pdf
│   └── 52148335_CARLOS_LOPEZ.pdf
└── SIN_FIRMANTE/
    └── 12345678_PACIENTE_SIN_FIRMA.pdf
```

---

## Tipos de examen soportados

| Tooltip en Sentinel | Código interno | Servicio en CEMDE |
|---|---|---|
| `ecg ambulatorio` | `HOLTER` | MONITOREO ELECTROCARDIOGRAFICO CONTINUO (HOLTER) |
| `mapa` | `MAPA` | MONITOREO AMBULATORIO DE PRESIÓN ARTERIAL SISTEMICA |
| `ecg 12 derivaciones` | `ELECTROCARDIOGRAMA` | ELECTROCARDIOGRAMA DE RITMO O DE SUPERFICIE SOD |

Para agregar un nuevo tipo, editar los dicts `MAPEO_TIPOS_EXAMEN` y `SERVICIOS_EXAMEN` en `config/settings.py`.

---

## Solución de problemas frecuentes

**El bot no encuentra el WebDriver de Edge**
Verificar que `msedgedriver.exe` esté en el PATH y que su versión coincida con la de Edge instalado (`edge://settings/help`).

**`TimeoutException` al buscar elementos**
La página tardó más de 25 segundos en responder. Aumentar el `timeout` en `core/driver.py`:
```python
driver, wait = crear_driver(timeout=40)
```

**PDF descargado con 0 KB**
La sesión expiró antes de la descarga. El bot re-usa las cookies del navegador; si Sentinel tiene un timeout corto, reducir el número de cédulas procesadas por ejecución.

**`StaleElementReferenceException` en la tabla**
Ocurre cuando la tabla se recarga entre iteraciones. El código ya maneja esto re-buscando las filas en cada ciclo (`driver.find_elements` dentro del `while`).

---

## Programar ejecución automática

**Windows — Task Scheduler:**
```
Programa : C:\ruta\venv\Scripts\python.exe
Argumentos: C:\ruta\bot_sentinel_cemde\main.py
Directorio: C:\ruta\bot_sentinel_cemde
```

**Linux / Mac — Cron (todos los días a las 7 AM):**
```bash
0 7 * * * cd /ruta/bot_sentinel_cemde && venv/bin/python main.py >> logs/cron.log 2>&1
```