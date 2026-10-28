import pytest

from modules.cemde import ayudas_diagnosticas as ad


@pytest.fixture
def cemde_simulado(monkeypatch, tmp_path):
    """
    CEMDE simulado, sin navegador ni esperas. Devuelve un objeto con:
      - fallan : set de cédulas que lanzan un error reintentable al abrir el paciente
      - abiertos : lista de cédulas con las que se llamó a abrir_paciente
    El resto de las cédulas llega hasta 'el examen ya estaba cargado'
    (éxito rápido, sin tocar el formulario).
    """
    class Simulacion:
        fallan: set[str]
        abiertos: list[str]

    sim = Simulacion()
    sim.fallan = set()
    sim.abiertos = []

    def abrir_paciente(driver, wait, cedula):
        sim.abiertos.append(cedula)
        if cedula in sim.fallan:
            raise Exception("boom")

    monkeypatch.setattr(ad, "abrir_paciente", abrir_paciente)
    monkeypatch.setattr(ad, "obtener_sede", lambda *a, **k: ("SEDE", None))
    monkeypatch.setattr(ad, "obtener_numero_sentinel", lambda *a, **k: None)
    monkeypatch.setattr(ad, "_abrir_formulario_otros_ad", lambda *a, **k: False)
    monkeypatch.setattr(ad.time, "sleep", lambda s: None)
    monkeypatch.chdir(tmp_path)
    return sim
