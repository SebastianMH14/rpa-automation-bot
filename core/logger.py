import logging
import os
from datetime import datetime
from config.settings import LOG_DIR


def setup_logger(name: str = "bot") -> logging.Logger:
    """
    Crea y devuelve un logger con salida a archivo y consola.
    Llamar UNA sola vez desde main.py; el resto de módulos
    hacen logging.getLogger("bot") para reutilizarlo.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    log_file = os.path.join(
        LOG_DIR, f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Archivo: nivel DEBUG (captura todo)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Consola: nivel INFO (solo lo relevante)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("📄 Log iniciado: %s", log_file)
    return logger
