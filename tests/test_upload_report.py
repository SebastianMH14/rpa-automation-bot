from utils.upload_report import UploadReport


def _pdf(nombre: str) -> dict:
    return {"nombre": nombre}


class TestAcumulacion:
    def test_ok_acumula_en_exitosos(self):
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        assert report._exitosos == ["a.pdf"]

    def test_reject_acumula_en_rechazados(self):
        report = UploadReport()
        report.reject(_pdf("a.pdf"))
        assert report._rechazados == [("a.pdf", "Examen rechazado")]

    def test_already_acumula_en_procesados(self):
        report = UploadReport()
        report.already(_pdf("a.pdf"))
        assert report._procesados == ["a.pdf"]

    def test_fail_acumula_en_fallidos_con_motivo(self):
        report = UploadReport()
        report.fail(_pdf("a.pdf"), Exception("algo salió mal"))
        assert report._fallidos == [("a.pdf", "algo salió mal")]


class TestCorridaLimpia:
    """
    Cubre la condición que decide si se envía el correo de reporte
    (ver main.py y ARCHITECTURE.md §6.4). El caso de aborto con 0 fallidos
    es regresión directa de un bug real: un correo se envió de más porque
    la condición original solo miraba `fallidos == 0`.
    """

    def test_todo_exitoso_es_corrida_limpia(self):
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        report.ok(_pdf("b.pdf"))
        assert report.corrida_limpia(total=2) is True

    def test_mezcla_sin_fallidos_es_corrida_limpia(self):
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        report.reject(_pdf("b.pdf"))
        report.already(_pdf("c.pdf"))
        assert report.corrida_limpia(total=3) is True

    def test_con_fallidos_no_es_corrida_limpia(self):
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        report.fail(_pdf("b.pdf"), "error")
        assert report.corrida_limpia(total=2) is False

    def test_aborto_con_cero_fallidos_no_es_corrida_limpia(self):
        # Regresión: un circuit breaker aborta antes de intentar el resto
        # de la lista, así que _fallidos queda vacío aunque casi nada se
        # haya procesado. fallidos == 0 por sí solo NO alcanza.
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        report.marcar_abortado("8 fallos consecutivos")
        assert len(report._fallidos) == 0
        assert report.corrida_limpia(total=100) is False

    def test_registros_sin_contabilizar_no_es_corrida_limpia(self):
        # total no coincide con lo acumulado: algo quedó sin procesar
        # aunque no se haya marcado explícitamente como fallido ni abortado.
        report = UploadReport()
        report.ok(_pdf("a.pdf"))
        assert report.corrida_limpia(total=5) is False

    def test_abortado_por_refleja_el_motivo(self):
        report = UploadReport()
        assert report.abortado_por is None
        report.marcar_abortado("motivo de prueba")
        assert report.abortado_por == "motivo de prueba"


class TestGuardar:
    def test_guardar_crea_archivo_con_resumen(self, tmp_path):
        report = UploadReport()
        report.ok(_pdf("exitoso.pdf"))
        report.fail(_pdf("fallido.pdf"), "timeout")
        ruta = tmp_path / "reporte.txt"

        report.guardar(str(ruta))

        contenido = ruta.read_text(encoding="utf-8")
        assert "Total procesados : 2" in contenido
        assert "Exitosos         : 1" in contenido
        assert "Fallidos         : 1" in contenido
        assert "exitoso.pdf" in contenido
        assert "fallido.pdf" in contenido
        assert "timeout" in contenido

    def test_guardar_crea_directorios_intermedios(self, tmp_path):
        report = UploadReport()
        ruta = tmp_path / "sub" / "dir" / "reporte.txt"

        report.guardar(str(ruta))

        assert ruta.exists()

    def test_guardar_marca_el_aborto_en_el_texto(self, tmp_path):
        report = UploadReport()
        report.marcar_abortado("8 fallos consecutivos sin éxito")
        ruta = tmp_path / "reporte.txt"

        report.guardar(str(ruta))

        contenido = ruta.read_text(encoding="utf-8")
        assert "ABORTADO" in contenido
        assert "8 fallos consecutivos sin éxito" in contenido
