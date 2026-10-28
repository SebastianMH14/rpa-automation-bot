from modules.cemde import ayudas_diagnosticas as ad


def _pdf(cedula: str) -> dict:
    return {
        "cedula": cedula,
        "nombre": f"{cedula}_PACIENTE_MAPA.pdf",
        "examen": "MAPA",
        "fecha_atencion": "01/10/2026 10:00:00",
        "estado": "CONFIRMADO",
        "firmante": None,
        "ruta": "x.pdf",
    }


def test_reintentos_con_fallos_no_disparan_el_corte(cemde_simulado):
    # Regresión 05/10/2026: 5 registros fallaban en la pasada principal
    # (intercalados con éxitos) y seguían fallando en los 2 reintentos. Los
    # fallos de los reintentos se sumaban a la racha, llegaban a 8 y la corrida,
    # que había procesado 775 de 777, se reportaba como "ABORTADA".
    cemde_simulado.fallan.update({"f1", "f2", "f3", "f4", "f5"})
    pdfs = []
    for c in ("f1", "f2", "f3", "f4", "f5"):
        pdfs += [_pdf(f"ok_{c}"), _pdf(c)]

    exitosos, fallidos, rechazados, procesados, report, _ = ad.subir_pdfs(
        None, None, pdfs)

    assert report.abortado_por is None
    assert fallidos == 5
    assert procesados == 5
    assert report.corrida_limpia(len(pdfs)) is False  # hay fallidos, pero no abortó


def test_fallo_sistematico_en_la_pasada_principal_si_aborta(cemde_simulado):
    # El corte sigue funcionando donde importa: 8 fallos seguidos sin ningún
    # éxito en la pasada principal.
    cedulas = [f"f{i}" for i in range(12)]
    cemde_simulado.fallan.update(cedulas)
    pdfs = [_pdf(c) for c in cedulas]

    _, fallidos, _, _, report, _ = ad.subir_pdfs(None, None, pdfs)

    assert report.abortado_por is not None
    assert "8 fallos consecutivos" in report.abortado_por
