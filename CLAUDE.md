# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # install dependencies
python main.py                    # run the full bot end-to-end (opens a visible Edge window)
```

There is no test suite, linter, or build step in this repository — it's a plain
Selenium automation script. `python -m py_compile <file>` is the fastest sanity
check after an edit (catches syntax errors without launching a browser).

Required env vars (`.env`, never committed): `URL_LOGIN_SENTINEL`, `USUARIO_SENTINEL`,
`PASSWORD_SENTINEL`, `URL_LOGIN_CEMDE`, `EMAIL_CEMDE`, `PASSWORD_CEMDE`, `URL_PACIENTES`,
and for the email report: `EMAIL_REMITENTE`, `EMAIL_PASSWORD`, `EMAIL_DESTINATARIOS`,
`EMAIL_SMTP_HOST`/`EMAIL_SMTP_PORT`. There is no `.env.example` in the repo despite the
README mentioning one — check with the user before assuming its shape.

To test against a small, controlled subset instead of the full backlog, set
`CEDULAS_PRUEBA` in `config/settings.py` to a non-empty set of cédulas — the bot
will fetch only those and stop once all are found. **Must be an empty set in
production**; a non-empty set silently limits every run to just those patients.

## Architecture

Two-system RPA pipeline: **Sentinel** (source of exam results) → **CEMDE**
(clinic's patient record system, target). `main.py` orchestrates in one
Selenium session: `login_sentinel` → `procesar_tabla_sentinel` (scrape +
download confirmed/rejected exam PDFs) → `login_cemde` → `subir_pdfs` (attach
each PDF to the right patient's record as an "ayuda diagnóstica") → conditional
email report.

- `modules/sentinel/` — login, paginated table scraping with per-row dedup
  against local `pdfs_descargados/`, and PDF download. Download does **not**
  use Selenium's download manager — it reuses the browser's cookies in a
  `requests.Session()` to fetch the PDF directly from the iframe's `GetPdf`
  URL (`verify=False`, since CEMDE is accessed by raw IP).
- `modules/cemde/` — login, patient lookup (`paciente.py`), nota de enfermería
  data extraction (`notas_enfermeria.py`), and the upload form
  (`ayudas_diagnosticas.py`, the most complex module — read it end to end
  before touching the upload flow, not just the function you're editing).
- `utils/select2.py` — two different Select2 helpers: `buscar_opcion_select`
  (simple client-rendered dropdowns) vs `buscar_opcion_select_lectura`
  (AJAX-backed dropdowns like `usuario_lectura`, needs debounced search +
  stale-element retries). Don't use the simple one on an AJAX field.
- `alpha.py` is a legacy monolithic prototype predating the `modules/` split.
  Not imported by `main.py` — dead code kept for reference, not a second
  entry point.

### CEMDE is a moving target — treat "no such element" as a UI-change signal first

CEMDE's frontend has changed twice already without notice, each time breaking
a previously-working selector across every single record in a run:
- The patient list page's search went from a live-search `<ul id="lista-pacientes">`
  dropdown to a DataTables table. `abrir_paciente` now filters
  `#pacientes-table_filter input[type='search']` and matches the **Documento**
  column exactly (`normalize-space(text())='{cedula}'`), never a substring —
  CEMDE's table can have a longer document number containing the searched one
  as a substring, which would open the wrong patient's chart.
- The form's "Guardar" submit control changed from `<input type="submit">` to
  `<button type="submit">` (same classes). Both submit buttons now accept
  either tag and pick the first *visible* match, because the page also has
  several hidden buttons sharing the same `btn green` class in unrelated
  modals.

If a selector that "always worked" suddenly fails on every record in a run,
suspect a CEMDE markup change before suspecting the data.

### Known race condition: notas de enfermería table renders in two stages

CEMDE's DataTables tables (patient notes, among others) render empty
"skeleton" `<tr>` rows immediately, then fill them with real content via AJAX
~2 seconds later. `wait.until(presence_of_element_located(...tr))` is
satisfied by the empty skeleton row, so reading cell text right after it can
silently return `''`, making `obtener_numero_sentinel` fail to find a real,
existing note. Use `_esperar_filas_notas_cargadas()` in
`modules/cemde/notas_enfermeria.py` (waits for at least one row with non-empty
first-cell text) instead of a bare presence wait — both call sites in that
file already do this; keep doing it in any new one.

### Equipo/marca/serial only apply to HOLTER and MAPA

`_completar_formulario` only looks up `select_equipo_medico_id`,
`select_marca_equipo`, and `select_codigo_serial` when `tipo_examen in
("HOLTER", "MAPA")`. ELECTROCARDIOGRAMA exams have no ambulatory equipment and
no matching nota de enfermería, so `sentinel_data` is `None` for them —
forcing these selects unconditionally (as an earlier version of this code
did) makes every ELECTROCARDIOGRAMA record fail. Confirmed live that CEMDE
accepts the form without these fields for that exam type.

### Circuit breaker and email gating in `subir_pdfs`

`subir_pdfs` (in `ayudas_diagnosticas.py`) aborts the whole run
(`_FalloSistematico`) after 8 consecutive failures with no success in
between, instead of exhausting all retry passes across the full pending list
— a systemic failure (e.g. a CEMDE UI change) previously burned hours
repeating the identical failure hundreds of times before this existed. An
aborted run still returns `fallidos == 0` for the records it never attempted,
so **never gate the email report on `fallidos == 0` alone** — also check
`report.abortado_por` and that `exitosos + rechazados + procesados == len(pdfs)`
before sending. This logic lives in `main.py`, not in `UploadReport`.

### Two independent dedup layers

A PDF already downloaded to `pdfs_descargados/<firmante>/<fecha>/<archivo>.pdf`
is skipped on the Sentinel side (`modules/sentinel/tabla.py`), but is still
attempted on the CEMDE side — `_abrir_formulario_otros_ad` separately checks
whether that exam/date is already loaded in CEMDE and skips only then. Don't
assume a locally-present PDF means it was already uploaded.

### Business logic lives in `config/settings.py`

`MAPEO_TIPOS_EXAMEN` (Sentinel tooltip → internal exam code) and
`SERVICIOS_EXAMEN` (internal code → CEMDE service name) are the only place
exam-type mappings are defined. Adding a new exam type means updating both
dicts, and deciding whether it needs nota de enfermería / equipo data (see
above) — don't hardcode a new mapping elsewhere.

### Failures that are data problems, not bugs

Recurring failure messages that mean "fix it in CEMDE, not in code": a
patient document number with no match at all in `#pacientes-table` (patient
not registered in CEMDE), a `select_codigo_serial` value with no matching
option (equipment not in CEMDE's catalog), or `planilla_ingreso`/sede not
found for a date (the appointment itself isn't registered in CEMDE). These
show up as sparse, non-consecutive failures across otherwise-healthy runs —
don't try to "fix" them by loosening matching logic.
