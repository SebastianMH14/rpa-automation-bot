import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def _resumir_error(error: Exception | str) -> str:
    """
    Deja solo la primera línea útil del error. Las excepciones de Selenium
    traen después un bloque "Stacktrace:" de frames del driver que no le
    sirve a quien lee el reporte (el detalle completo queda en el log).
    """
    texto = str(error).split("Stacktrace:")[0].strip()
    for linea in texto.splitlines():
        if linea.strip():
            return linea.strip()
    return texto


class UploadReport:
    def __init__(self):
        self._exitosos:   list[str] = []
        self._rechazados: list[tuple[str, str]] = []
        self._fallidos:   list[tuple[str, str]] = []
        self._procesados: list[str] = []
        self._abortado_por: str | None = None

    def marcar_abortado(self, motivo: str) -> None:
        """Marca el reporte como resultado de una corrida que se detuvo antes
        de procesar todos los registros: aborto por fallos sistemáticos (ver
        `_FalloSistematico` en ayudas_diagnosticas.py) o error fatal."""
        self._abortado_por = _resumir_error(motivo)

    @property
    def abortado_por(self) -> str | None:
        """Motivo del aborto temprano, o None si la corrida no fue abortada.
        Un aborto puede dejar `fallidos == 0` (los pendientes nunca se
        contabilizan) — por eso, para saber si la corrida salió bien, no
        alcanza con mirar solo `fallidos`; ver `corrida_limpia`."""
        return self._abortado_por

    def corrida_limpia(self, total: int) -> bool:
        """
        True solo si la corrida terminó genuinamente limpia: sin fallidos,
        sin aborto por circuit breaker, y con los `total` PDFs esperados
        contabilizados en alguna categoría (exitoso/rechazado/ya procesado).

        Las tres condiciones son necesarias — en particular, un aborto por
        fallos sistemáticos deja `_fallidos` vacío (los registros nunca
        intentados no se contabilizan como fallidos), así que mirar solo
        `len(self._fallidos) == 0` da un falso positivo y haría pasar por
        exitosa una corrida que en realidad no subió casi nada. Se usa para
        el código de salida del proceso; el correo se envía siempre.

        Args:
            total: cantidad total de PDFs que la corrida debía procesar
                   (`len(pdfs)` en el llamador).
        """
        return (
            len(self._fallidos) == 0
            and not self._abortado_por
            and len(self._exitosos) + len(self._rechazados) + len(self._procesados) == total
        )

    def ok(self, pdf: dict) -> None:
        """Registra un PDF subido correctamente."""
        self._exitosos.append(pdf["nombre"])

    def reject(self, pdf: dict) -> None:
        """Registra un PDF rechazado (descartado por regla de negocio)."""
        self._rechazados.append((pdf["nombre"], "Examen rechazado"))

    def fail(self, pdf: dict, error: Exception | str) -> None:
        """Registra un PDF que falló con su error."""
        self._fallidos.append((pdf["nombre"], _resumir_error(error)))

    def already(self, pdf: dict) -> None:
        """Registra un PDF que ya había sido procesado anteriormente."""
        self._procesados.append(pdf["nombre"])

    def guardar(self, ruta: str) -> None:
        """Escribe el reporte en *ruta*. Crea los directorios si no existen."""
        os.makedirs(os.path.dirname(ruta), exist_ok=True)

        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        total = (
            len(self._exitosos)
            + len(self._rechazados)
            + len(self._fallidos)
            + len(self._procesados)
        )
        lineas: list[str] = []

        lineas.append("=" * 60)
        lineas.append(f"  REPORTE DE CARGA  —  {ahora}")
        lineas.append("=" * 60)

        if self._abortado_por:
            lineas.append("")
            lineas.append("⛔ PROCESO ABORTADO")
            lineas.append(f"   Motivo: {self._abortado_por}")
            lineas.append(
                "   La corrida se detuvo antes de procesar todos los "
                "registros. Revisar manualmente CEMDE/Sentinel antes de la "
                "próxima ejecución."
            )
            lineas.append("")
        lineas.append(f"  Total procesados : {total}")
        lineas.append(f"  Exitosos         : {len(self._exitosos)}")
        lineas.append(f"  Rechazados       : {len(self._rechazados)}")
        lineas.append(f"  Ya procesados    : {len(self._procesados)}")
        lineas.append(f"  Fallidos         : {len(self._fallidos)}")
        lineas.append("=" * 60)

        # ── Exitosos ──────────────────────────────────────────────────
        lineas.append("")
        lineas.append(f"✅ EXITOSOS ({len(self._exitosos)})")
        lineas.append("-" * 60)
        if self._exitosos:
            for nombre in self._exitosos:
                lineas.append(f"  • {nombre}")
        else:
            lineas.append("  (ninguno)")

        # ── Rechazados ────────────────────────────────────────────────
        lineas.append("")
        lineas.append(f"⚠️  RECHAZADOS ({len(self._rechazados)})")
        lineas.append("-" * 60)
        if self._rechazados:
            for nombre, motivo in self._rechazados:
                lineas.append(f"  • {nombre}")
                lineas.append(f"    Motivo: {motivo}")
        else:
            lineas.append("  (ninguno)")

        # ── Ya procesados ─────────────────────────────────────────────
        lineas.append("")
        lineas.append(f"🔁 YA PROCESADOS ({len(self._procesados)})")
        lineas.append("-" * 60)
        if self._procesados:
            for nombre in self._procesados:
                lineas.append(f"  • {nombre}")
        else:
            lineas.append("  (ninguno)")

        # ── Fallidos ──────────────────────────────────────────────────
        lineas.append("")
        lineas.append(f"❌ FALLIDOS ({len(self._fallidos)})")
        lineas.append("-" * 60)
        if self._fallidos:
            for nombre, error in self._fallidos:
                lineas.append(f"  • {nombre}")
                lineas.append(f"    Error: {error}")
        else:
            lineas.append("  (ninguno)")

        lineas.append("")
        lineas.append("=" * 60)

        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))

    def enviar_email(self, ruta_reporte: str) -> bool:
        """
        Envía el reporte final por correo electrónico.

        Lee las credenciales desde las variables de entorno:
            EMAIL_REMITENTE     — cuenta desde la que se envía (ej. bot@gmail.com)
            EMAIL_PASSWORD      — contraseña o app-password del remitente
            EMAIL_DESTINATARIOS — destinatarios separados por coma
            EMAIL_SMTP_HOST     — servidor SMTP  (default: smtp.gmail.com)
            EMAIL_SMTP_PORT     — puerto SMTP    (default: 587)

        Retorna True si el envío fue exitoso, False en caso de error.
        """
        from config.settings import (
            EMAIL_REMITENTE,
            EMAIL_PASSWORD,
            EMAIL_DESTINATARIOS,
            EMAIL_SMTP_HOST,
            EMAIL_SMTP_PORT,
        )

        if not EMAIL_REMITENTE or not EMAIL_PASSWORD or not EMAIL_DESTINATARIOS:
            raise ValueError(
                "Faltan variables de entorno para el correo: "
                "EMAIL_REMITENTE, EMAIL_PASSWORD y EMAIL_DESTINATARIOS son obligatorias."
            )

        total = (
            len(self._exitosos)
            + len(self._rechazados)
            + len(self._fallidos)
            + len(self._procesados)
        )
        estado = "✅ Sin errores" if not self._fallidos else f"⚠️ {len(self._fallidos)} fallido(s)"
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

        # ── Asunto ────────────────────────────────────────────────────
        if self._abortado_por:
            asunto = f"[RPA Bot] ⛔ PROCESO ABORTADO — {ahora} — revisar CEMDE/Sentinel"
        else:
            asunto = (
                f"[RPA Bot] Reporte de carga — {ahora} — "
                f"{len(self._exitosos)} exitosos / {total} total — {estado}"
            )

        # ── Cuerpo HTML ───────────────────────────────────────────────
        def _filas(items, cols=1):
            if not items:
                return "<tr><td colspan='2' style='color:#888'>(ninguno)</td></tr>"
            if cols == 1:
                return "".join(
                    f"<tr><td style='padding:2px 8px'>• {n}</td></tr>" for n in items
                )
            return "".join(
                f"<tr><td style='padding:2px 8px'>• {n}</td>"
                f"<td style='padding:2px 8px;color:#c00'>{e}</td></tr>"
                for n, e in items
            )

        banner_abortado = ""
        if self._abortado_por:
            banner_abortado = f"""
            <div style="background:#fdecea;border:1px solid #c00;color:#900;
                        padding:10px 14px;margin-bottom:16px;border-radius:4px">
              <b>⛔ Proceso abortado.</b><br>
              Motivo: {self._abortado_por}<br>
              La corrida se detuvo antes de procesar todos los registros.
              Revisar manualmente CEMDE/Sentinel antes de la próxima ejecución.
            </div>
            """

        cuerpo_html = f"""
        <html><body style="font-family:monospace;font-size:13px">
        <h2 style="color:#333">📋 Reporte de Carga RPA — {ahora}</h2>
        {banner_abortado}
        <table style="border-collapse:collapse;margin-bottom:16px">
          <tr><td style="padding:4px 12px"><b>Total procesados</b></td><td>{total}</td></tr>
          <tr><td style="padding:4px 12px"><b>✅ Exitosos</b></td><td>{len(self._exitosos)}</td></tr>
          <tr><td style="padding:4px 12px"><b>⚠️ Rechazados</b></td><td>{len(self._rechazados)}</td></tr>
          <tr><td style="padding:4px 12px"><b>🔁 Ya procesados</b></td><td>{len(self._procesados)}</td></tr>
          <tr><td style="padding:4px 12px"><b>❌ Fallidos</b></td><td style="color:#c00"><b>{len(self._fallidos)}</b></td></tr>
        </table>

        <h3>✅ Exitosos</h3>
        <table>{_filas(self._exitosos)}</table>

        <h3>⚠️ Rechazados</h3>
        <table>{_filas(self._rechazados, cols=2)}</table>

        <h3>🔁 Ya procesados</h3>
        <table>{_filas(self._procesados)}</table>

        <h3>❌ Fallidos</h3>
        <table>{_filas(self._fallidos, cols=2)}</table>

        <p style="color:#888;font-size:11px;margin-top:24px">
          Reporte adjunto en texto plano. Generado automáticamente por RPA Bot.
        </p>
        </body></html>
        """

        # ── Armar mensaje ─────────────────────────────────────────────
        destinatarios = [d.strip() for d in EMAIL_DESTINATARIOS.split(",") if d.strip()]

        msg = MIMEMultipart("mixed")
        msg["Subject"] = asunto
        msg["From"] = EMAIL_REMITENTE
        msg["To"] = ", ".join(destinatarios)

        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

        # ── Adjuntar el .txt del reporte ──────────────────────────────
        if ruta_reporte and os.path.isfile(ruta_reporte):
            with open(ruta_reporte, "rb") as f:
                parte = MIMEBase("application", "octet-stream")
                parte.set_payload(f.read())
            encoders.encode_base64(parte)
            nombre_archivo = os.path.basename(ruta_reporte)
            parte.add_header(
                "Content-Disposition",
                f'attachment; filename="{nombre_archivo}"',
            )
            msg.attach(parte)

        # ── Enviar ────────────────────────────────────────────────────
        try:
            with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.ehlo()
                servidor.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
                servidor.sendmail(EMAIL_REMITENTE, destinatarios, msg.as_bytes())
            return True
        except smtplib.SMTPAuthenticationError as e:
            raise RuntimeError(
                f"Error de autenticación SMTP. Verifica EMAIL_REMITENTE y EMAIL_PASSWORD. Detalle: {e}"
            ) from e
        except smtplib.SMTPException as e:
            raise RuntimeError(f"Error SMTP al enviar el correo: {e}") from e
        except OSError as e:
            raise RuntimeError(
                f"No se pudo conectar a {EMAIL_SMTP_HOST}:{EMAIL_SMTP_PORT} — {e}"
            ) from e
