import os

from modules.cemde import ayudas_diagnosticas as ad
from modules.sentinel import tabla


def _pdf(cedula: str) -> dict:
    return {
        "cedula": cedula,
        "nombre": f"{cedula}_PACIENTE_HOLTER.pdf",
        "examen": "HOLTER",
        "fecha_atencion": "22/10/2026 9:07:00",
        "estado": "CONFIRMADO",
        "firmante": None,
        "ruta": "x.pdf",
    }


def _invalido(cedula: str) -> dict:
    return tabla._informe_invalido(
        cedula, "PACIENTE UNO", f"{cedula}_PACIENTE_HOLTER.pdf",
        "22/10/2026 9:07:00", "HOLTER", "CONFIRMADO",
        "no corresponde al paciente: ID dentro del PDF 98710328")


class TestSubirPdfsConInformesInvalidos:
    def test_se_reporta_como_fallido_y_no_se_toca_cemde(self, cemde_simulado):
        pdfs = [_pdf("bueno"), _invalido("ajeno")]

        exitosos, fallidos, _, procesados, report, _ = ad.subir_pdfs(None, None, pdfs)

        assert cemde_simulado.abiertos == ["bueno"]   # nunca se abrió al paciente ajeno
        assert fallidos == 1
        assert procesados == 1
        motivo = report._fallidos[0][1]
        assert "Informe descartado" in motivo and "98710328" in motivo

    def test_no_se_reintenta(self, cemde_simulado):
        # Con 2 pasadas de reintento, un fallo de CEMDE se repite 3 veces;
        # un informe descartado debe quedar en un solo intento (y ninguno en CEMDE).
        ad.subir_pdfs(None, None, [_invalido("ajeno")])
        assert cemde_simulado.abiertos == []

    def test_no_cuentan_para_el_circuit_breaker(self, cemde_simulado):
        # 12 informes descartados seguidos no son un fallo sistemático de CEMDE.
        pdfs = [_invalido(f"x{i}") for i in range(12)] + [_pdf("bueno")]

        _, fallidos, _, procesados, report, _ = ad.subir_pdfs(None, None, pdfs)

        assert report.abortado_por is None
        assert fallidos == 12
        assert procesados == 1   # el bueno sí se procesó

    def test_la_corrida_no_queda_limpia(self, cemde_simulado):
        pdfs = [_pdf("bueno"), _invalido("ajeno")]
        *_, report, _ = ad.subir_pdfs(None, None, pdfs)
        assert report.corrida_limpia(len(pdfs)) is False


class TestDescartarPdf:
    def test_aparta_el_archivo_sin_borrarlo(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tabla, "DOWNLOAD_DIR", str(tmp_path))
        origen = tmp_path / "SIN_FIRMANTE" / "2026-10-22" / "11221279_X_HOLTER.pdf"
        origen.parent.mkdir(parents=True)
        origen.write_bytes(b"%PDF-contenido")

        tabla._descartar_pdf(str(origen))

        assert not origen.exists()
        guardados = os.listdir(tmp_path / tabla.CARPETA_DESCARTADOS)
        assert len(guardados) == 1 and guardados[0].endswith("11221279_X_HOLTER.pdf")
        assert (tmp_path / tabla.CARPETA_DESCARTADOS / guardados[0]).read_bytes() == b"%PDF-contenido"

    def test_la_entrada_invalida_no_lleva_ruta_ni_firmante(self):
        e = _invalido("ajeno")
        assert e["ruta"] is None and e["firmante"] is None
        assert e["invalido"].startswith("Informe descartado")
