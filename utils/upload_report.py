import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


class UploadReport:
    def __init__(self):
        self._exitosos:   list[str] = []
        self._rechazados: list[tuple[str, str]] = []
        self._fallidos:   list[tuple[str, str]] = []
        self._procesados: list[str] = []

    def ok(self, pdf: dict) -> None:
        """Registra un PDF subido correctamente."""
        self._exitosos.append(pdf["nombre"])

    def reject(self, pdf: dict) -> None:
        """Registra un PDF rechazado (descartado por regla de negocio)."""
        self._rechazados.append((pdf["nombre"], "Examen rechazado"))

    def fail(self, pdf: dict, error: Exception | str) -> None:
        """Registra un PDF que falló con su error."""
        self._fallidos.append((pdf["nombre"], str(error)))

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

        cuerpo_html = f"""
        <html><body style="font-family:monospace;font-size:13px">
        <h2 style="color:#333">📋 Reporte de Carga RPA — {ahora}</h2>
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
