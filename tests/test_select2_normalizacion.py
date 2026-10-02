from utils.select2 import _limpiar_nombre_firmante, _normalizar_nombre_busqueda


class TestLimpiarNombreFirmante:
    def test_quita_sufijo_entre_parentesis(self):
        assert _limpiar_nombre_firmante(
            "Luz Adriana Ocampo A. (CEMDE)") == "Luz Adriana Ocampo A."

    def test_quita_prefijo_de_cargo(self):
        assert _limpiar_nombre_firmante("Dr. Juan Pérez (CEMDE)") == "Juan Pérez"

    def test_quita_prefijo_cardiologa(self):
        assert _limpiar_nombre_firmante(
            "Cardióloga Luz Adriana Ocampo A. (CEMDE)") == "Luz Adriana Ocampo A."

    def test_sin_prefijo_ni_parentesis_no_cambia(self):
        assert _limpiar_nombre_firmante(
            "Eiman Damian Moreno Pallares") == "Eiman Damian Moreno Pallares"

    def test_sufijo_de_sede_distinta_a_cemde(self):
        # Visto en producción: el firmante puede traer sedes como (CSAS)
        assert _limpiar_nombre_firmante(
            "Eiman Damian Moreno Pallares (CSAS)") == "Eiman Damian Moreno Pallares"


class TestNormalizarNombreBusqueda:
    def test_reduce_a_primeros_tres_tokens(self):
        assert _normalizar_nombre_busqueda(
            "Eiman Damian Moreno Pallares") == "Eiman Damian Moreno"

    def test_quita_abreviaciones_de_un_caracter(self):
        assert _normalizar_nombre_busqueda(
            "Luz Adriana Ocampo A.") == "Luz Adriana Ocampo"

    def test_nombre_de_dos_tokens_no_cambia(self):
        assert _normalizar_nombre_busqueda("Juan Pérez") == "Juan Pérez"

    def test_pipeline_completo_firmante_real(self):
        # Caso real: "Cardióloga Luz Adriana Ocampo A. (CEMDE)" debe terminar
        # siendo buscable en CEMDE como "Luz Adriana Ocampo".
        limpio = _limpiar_nombre_firmante(
            "Cardióloga Luz Adriana Ocampo A. (CEMDE)")
        assert _normalizar_nombre_busqueda(limpio) == "Luz Adriana Ocampo"
