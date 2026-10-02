import sys
from core.logger import setup_logger
from core.driver import crear_driver
from modules.sentinel.login import login_sentinel
from modules.sentinel.tabla import procesar_tabla_sentinel
from modules.cemde.login import login_cemde
from modules.cemde.ayudas_diagnosticas import subir_pdfs

logger = setup_logger("bot")


def main() -> int:
    driver, wait = crear_driver()

    try:
        # ── SENTINEL ──────────────────────────────────────────────────────
        login_sentinel(driver, wait)
        pdfs = procesar_tabla_sentinel(driver, wait)

        logger.info("PDFs listos para subir: %d", len(pdfs))

        if not pdfs:
            logger.warning("⚠ No hay PDFs que subir. Finalizando.")
            return 0

        # ── CEMDE ─────────────────────────────────────────────────────────
        login_cemde(driver, wait)
        exitosos, fallidos, rechazados, procesados, reporte, ruta_reporte = subir_pdfs(
            driver, wait, pdfs
        )

    except Exception as e:
        logger.critical("💥 Error fatal no controlado: %s", e, exc_info=True)
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
    # Solo se envía si la corrida terminó realmente limpia (ver
    # UploadReport.corrida_limpia): sin fallidos, sin aborto por circuit
    # breaker y con todos los PDFs contabilizados en alguna categoría.
    corrida_limpia = reporte.corrida_limpia(len(pdfs))

    if corrida_limpia:
        logger.info("✅ Corrida limpia (0 fallidos, sin abortos, todo procesado) — enviando correo de reporte")
        try:
            reporte.enviar_email(ruta_reporte)
            logger.info("📧 Reporte enviado por correo correctamente")
        except Exception as e:
            logger.error("📧 No se pudo enviar el reporte por correo: %s", e)
    elif reporte.abortado_por:
        logger.warning(
            "🚫 Correo SUPRIMIDO — proceso abortado por fallos sistemáticos "
            "(%d/%d registros nunca se intentaron). Motivo: %s",
            len(pdfs) - (exitosos + rechazados + procesados + fallidos),
            len(pdfs), reporte.abortado_por,
        )
    else:
        logger.warning(
            "🚫 Correo SUPRIMIDO — quedan %d fallidos pendientes de corregir. "
            "Se enviará solo cuando una corrida termine con 0 fallidos y sin abortos.",
            fallidos,
        )

    return 0 if corrida_limpia else 1


if __name__ == "__main__":
    sys.exit(main())
