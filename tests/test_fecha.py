from datetime import datetime

import pytest

from utils.fecha import fecha_solo_dia, parse_fecha, sentinel_a_input


class TestFechaSoloDia:
    def test_extrae_la_parte_de_fecha(self):
        assert fecha_solo_dia("15/03/2024 08:30:00") == "15/03/2024"

    def test_sin_componente_de_hora_devuelve_igual(self):
        assert fecha_solo_dia("15/03/2024") == "15/03/2024"


class TestSentinelAInput:
    def test_convierte_formato_sentinel_a_iso(self):
        assert sentinel_a_input("15/03/2024 08:30:00") == "2024-03-15"

    def test_formato_invalido_lanza_value_error(self):
        with pytest.raises(ValueError):
            sentinel_a_input("2024-03-15")


class TestParseFecha:
    def test_acepta_formato_iso(self):
        assert parse_fecha("2024-03-15") == datetime(2024, 3, 15)

    def test_acepta_formato_dd_mm_yyyy(self):
        assert parse_fecha("15/03/2024") == datetime(2024, 3, 15)

    def test_formato_no_reconocido_devuelve_none(self):
        assert parse_fecha("15 de marzo de 2024") is None

    def test_cadena_vacia_devuelve_none(self):
        assert parse_fecha("") is None
