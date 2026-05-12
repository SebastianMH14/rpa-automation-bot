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
        exitosos, fallidos, rechazados, procesados = subir_pdfs(driver, wait, pdfs)

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

    return 0 if fallidos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
