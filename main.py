import os
import sys
from datetime import datetime
from core.logger import setup_logger
from core.driver import crear_driver
from modules.sentinel.login import login_sentinel
from modules.sentinel.tabla import procesar_tabla_sentinel
from modules.cemde.login import login_cemde
from modules.cemde.ayudas_diagnosticas import subir_pdfs
from utils.upload_report import UploadReport

logger = setup_logger("bot")


def _enviar_reporte(reporte: UploadReport, ruta_reporte: str) -> None:
    """El correo se envía siempre al terminar, sea cual sea el resultado: el
    cliente debe enterarse de cómo salió la corrida. Un fallo al enviarlo se
    registra pero no cambia el código de salida."""
    try:
        reporte.enviar_email(ruta_reporte)
        logger.info("📧 Reporte enviado por correo correctamente")
    except Exception as e:
        logger.error("📧 No se pudo enviar el reporte por correo: %s", e)


def _reporte_sin_subidas(motivo: str | None = None) -> tuple[UploadReport, str]:
    """Reporte para las corridas que terminan sin pasar por `subir_pdfs`
    (nada pendiente, o error fatal antes de terminar)."""
    reporte = UploadReport()
    if motivo:
        reporte.marcar_abortado(motivo)
    ruta = os.path.join(
        "logs", f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    reporte.guardar(ruta)
    return reporte, ruta


def main() -> int:
    driver, wait = crear_driver()

    try:
        # ── SENTINEL ──────────────────────────────────────────────────────
        login_sentinel(driver, wait)
        pdfs = procesar_tabla_sentinel(driver, wait)

        logger.info("PDFs listos para subir: %d", len(pdfs))

        if not pdfs:
            logger.warning("⚠ No hay PDFs que subir. Finalizando.")
            _enviar_reporte(*_reporte_sin_subidas())
            return 0

        # ── CEMDE ─────────────────────────────────────────────────────────
        login_cemde(driver, wait)
        exitosos, fallidos, rechazados, procesados, reporte, ruta_reporte = subir_pdfs(
            driver, wait, pdfs
        )

    except Exception as e:
        logger.critical("💥 Error fatal no controlado: %s", e, exc_info=True)
        _enviar_reporte(*_reporte_sin_subidas(
            f"Error fatal no controlado: {type(e).__name__}: {e}"))
        return 1

    finally:
        driver.quit()
        logger.info("🔒 Navegador cerrado")

    # ── RESUMEN FINAL ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🎉 PROCESO COMPLETADO")
    logger.info("   PDFs procesados : %d", len(pdfs))
    logger.info("   ✅ Exitosos      : %d", exitosos)
    logger.info("   ❌ Fallidos      : %d", fallidos)
    logger.info("   ⚠️  Rechazados    : %d", rechazados)
    logger.info("   🔁 Ya procesados : %d", procesados)
    logger.info("=" * 60)

    # ── ENVÍO DE REPORTE POR CORREO ────────────────────────────────────────
    # Siempre se envía; el asunto y el cuerpo ya reflejan si hubo fallidos o
    # aborto. corrida_limpia solo decide el código de salida.
    _enviar_reporte(reporte, ruta_reporte)

    return 0 if reporte.corrida_limpia(len(pdfs)) else 1


if __name__ == "__main__":
    sys.exit(main())
