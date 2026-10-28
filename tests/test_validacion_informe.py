import pytest

from utils import validacion_informe as vi

# Textos tomados de los informes reales del incidente del 24/10/2026.
HOLTER_RINCON = (
    "CEMDE RINCON RODRIGUEZ, ANDRES EDUARDO Informe Holter de derivaciones 3\n"
    "ID paciente: 11221279, Fecha de nacimiento: sáb 16 abr. 1977 (49 años) Sexo: Hombre"
)
ECG_ORTEGA = (
    "Spacelabs Healthcare Sentinel - Informe de ECG\n"
    "Paciente\nNombre: ORTEGA, ANDRES MAURICIO\nID paciente: 98710328\n"
    "ID nacional:\nFecha de nacimiento: 23/01/1983\nEdad: 43 años\nNo confirmado"
)
PLANTILLA_VACIA = (
    "CEMDE | No confirmado Informe de MAPA de Sentinel\n"
    "ID paciente: Nombre del paciente:\nFecha de nacimiento: Sexo:"
)


class TestInformeCorresponde:
    def test_id_coincide_aunque_el_pdf_traiga_coma_final(self):
        ok, _ = vi.informe_corresponde(
            "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO", HOLTER_RINCON)
        assert ok is True

    def test_regresion_ecg_de_otra_persona_no_corresponde(self):
        # El caso real: el bot guardó el ECG de Ortega con el nombre de Rincón.
        # Comparten una sola palabra ("ANDRES"), así que no basta el nombre.
        ok, motivo = vi.informe_corresponde(
            "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO", ECG_ORTEGA)
        assert ok is False
        assert "98710328" in motivo

    def test_id_mal_digitado_pero_mismo_nombre_si_corresponde(self):
        # Caso real: Sentinel tiene 3528179 en la lista y 358179 en el informe.
        texto = ("CEMDE HINCAPIE VALLEJO, BERNARDO DE\nJESUS Informe Holter de derivaciones 3\n"
                 "ID paciente: 358179 Fecha de nacimiento: vie 10 ago. 1951")
        ok, _ = vi.informe_corresponde(
            "3528179", "HINCAPIE VALLEJO BERNARDO DE JESUS", texto)
        assert ok is True

    def test_id_con_un_digito_de_mas_y_mismo_nombre(self):
        texto = "CEMDE ALZATE ABREU, ASHLEY JANETH Informe Holter\nID paciente: 112845760"
        ok, _ = vi.informe_corresponde(
            "1128457602", "ALZATE ABREU ASHLEY JANETH", texto)
        assert ok is True

    def test_otra_persona_con_id_y_nombre_distintos(self):
        texto = ("Generado el do. 11 oct. 2026 MAPA de Sentinel\n"
                 "ID paciente: 43190750 Nombre del paciente: DIANA CAROLINA VELILLA")
        ok, _ = vi.informe_corresponde(
            "43495558", "SáNCHEZ GALLEGO MARINA DEL SOCORRO", texto)
        assert ok is False

    def test_plantilla_vacia_sin_paciente_no_corresponde(self):
        ok, _ = vi.informe_corresponde(
            "70504375", "SOSA RESTREPO WILLIAM", PLANTILLA_VACIA)
        assert ok is False

    def test_un_apellido_en_comun_no_alcanza(self):
        texto = "CEMDE GARCIA PEREZ, JOSE Informe Holter\nID paciente: 99999999"
        ok, _ = vi.informe_corresponde(
            "8270479", "GARCIA CORREA JOSE DELIO", texto)
        assert ok is False

    def test_nombre_corto_exige_todas_las_palabras(self):
        assert vi.informe_corresponde(
            "1", "BEDOYA ELENA", "BEDOYA, ELENA ID paciente: 7")[0] is True
        assert vi.informe_corresponde(
            "1", "BEDOYA ELENA", "BEDOYA, MARIA ID paciente: 7")[0] is False

    def test_tilde_o_enie_perdida_en_el_pdf_no_rompe_el_nombre(self):
        # pypdf a veces devuelve "�" en lugar de "Ñ" o una vocal con tilde.
        texto = "CEMDE MU�OZ GOMEZ, ANA MARIA Informe Holter\nID paciente: 555"
        ok, _ = vi.informe_corresponde("1", "MUÑOZ GOMEZ ANA MARIA", texto)
        assert ok is True

    def test_cedula_alfanumerica_compara_igual_que_la_fila(self):
        texto = "ID paciente: NS35FF9R7 Nombre: X"
        ok, _ = vi.informe_corresponde("NS35FF9R7", "ROBERTO ANGELA ALEJANDRO", texto)
        assert ok is True


class TestEncabezado:
    def test_parsea_nombre_e_id(self):
        assert vi.parsear_encabezado(
            "Revisar informe - ANDRES EDUARDO RINCON RODRIGUEZ (11221279,)"
        ) == ("ANDRES EDUARDO RINCON RODRIGUEZ", "11221279,")

    def test_sin_encabezado_devuelve_none(self):
        assert vi.parsear_encabezado("Otra pantalla cualquiera") is None

    def test_encabezado_del_mismo_paciente_con_nombre_en_otro_orden(self):
        ok, _ = vi.encabezado_corresponde(
            "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO",
            "ANDRES EDUARDO RINCON RODRIGUEZ", "11221279,")
        assert ok is True

    def test_encabezado_de_otro_paciente_no_corresponde(self):
        ok, motivo = vi.encabezado_corresponde(
            "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO",
            "ANDRES MAURICIO ORTEGA", "98710328")
        assert ok is False
        assert "ORTEGA" in motivo


class TestValidarPdf:
    def test_pdf_que_no_se_puede_leer_no_es_valido(self, monkeypatch):
        def boom(ruta):
            raise OSError("archivo dañado")
        monkeypatch.setattr(vi, "leer_texto_primera_pagina", boom)
        ok, motivo = vi.validar_pdf("x.pdf", "1", "NOMBRE APELLIDO UNO")
        assert ok is False
        assert "no se pudo leer" in motivo

    def test_falta_de_pypdf_no_se_confunde_con_un_pdf_ilegible(self, monkeypatch):
        # Si faltara la dependencia, devolver "no válido" apartaría TODOS los
        # PDFs de la corrida: el error debe propagarse, no convertirse en motivo.
        def sin_pypdf(ruta):
            raise ImportError("No module named 'pypdf'")
        monkeypatch.setattr(vi, "leer_texto_primera_pagina", sin_pypdf)
        with pytest.raises(ImportError):
            vi.validar_pdf("x.pdf", "1", "NOMBRE APELLIDO UNO")

    def test_verificar_dependencias_pasa_con_pypdf_instalado(self):
        vi.verificar_dependencias()

    def test_verificar_dependencias_falla_si_no_esta_pypdf(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "pypdf", None)   # simula no instalado
        with pytest.raises(ImportError):
            vi.verificar_dependencias()

    def test_pdf_legible_se_valida_contra_la_fila(self, monkeypatch):
        monkeypatch.setattr(vi, "leer_texto_primera_pagina", lambda r: ECG_ORTEGA)
        assert vi.validar_pdf(
            "x.pdf", "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO")[0] is False
        monkeypatch.setattr(vi, "leer_texto_primera_pagina", lambda r: HOLTER_RINCON)
        assert vi.validar_pdf(
            "x.pdf", "11221279,", "RINCON RODRIGUEZ ANDRES EDUARDO")[0] is True


class TestVisitas:
    def test_segunda_visita_al_mismo_examen_se_detecta(self):
        visitados = set()
        assert vi.registrar_visita(visitados, "11221279,", "HOLTER", "22/10/2026 9:07:00") is False
        assert vi.registrar_visita(visitados, "11221279,", "HOLTER", "22/10/2026 9:07:00") is True

    def test_la_coma_final_de_la_cedula_no_crea_otro_examen(self):
        visitados = set()
        vi.registrar_visita(visitados, "11221279,", "HOLTER", "22/10/2026 9:07:00")
        assert vi.registrar_visita(visitados, "11221279", "HOLTER", "22/10/2026 9:07:00") is True

    @pytest.mark.parametrize("cedula,examen,fecha", [
        ("11221279", "MAPA", "22/10/2026 9:07:00"),        # otro tipo de examen
        ("11221279", "HOLTER", "22/10/2026 9:08:00"),      # otra hora
        ("11221280", "HOLTER", "22/10/2026 9:07:00"),      # otro paciente
    ])
    def test_examenes_distintos_no_se_consideran_repetidos(self, cedula, examen, fecha):
        visitados = set()
        vi.registrar_visita(visitados, "11221279", "HOLTER", "22/10/2026 9:07:00")
        assert vi.registrar_visita(visitados, cedula, examen, fecha) is False
