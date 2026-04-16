from datetime import datetime


class UploadReport:
    def __init__(self):
        self._exitosos: list[str] = []
        self._fallidos: list[tuple[str, str]] = []

    def ok(self, pdf: dict) -> None:
        """Registra un PDF subido correctamente."""
        self._exitosos.append(pdf["nombre"])

    def fail(self, pdf: dict, error: Exception | str) -> None:
        """Registra un PDF que falló con su error."""
        self._fallidos.append((pdf["nombre"], str(error)))

    def guardar(self, ruta: str) -> None:
        """Escribe el reporte en *ruta*. Crea los directorios si no existen."""
        import os
        os.makedirs(os.path.dirname(ruta), exist_ok=True)

        ahora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        lineas: list[str] = []

        lineas.append("=" * 60)
        lineas.append(f"  REPORTE DE CARGA  —  {ahora}")
        lineas.append("=" * 60)
        lineas.append(
            f"  Total procesados : {len(self._exitosos) + len(self._fallidos)}"
        )
        lineas.append(f"  Exitosos         : {len(self._exitosos)}")
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
