from datetime import datetime


def fecha_solo_dia(fecha_str: str) -> str:
    """
    Extrae la parte 'YYYY-MM-DD' o 'DD/MM/YYYY' de un string de fecha.
    Ejemplo: '15/03/2024 08:30:00' → '15/03/2024'
    """
    return fecha_str.split(" ")[0]


def sentinel_a_input(fecha_str: str) -> str:
    """
    Convierte la fecha de Sentinel (DD/MM/YYYY HH:MM:SS) al formato
    requerido por el input HTML del formulario CEMDE (YYYY-MM-DD).
    Ejemplo: '15/03/2024 08:30:00' → '2024-03-15'
    """
    return datetime.strptime(fecha_str, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d")


def parse_fecha(fecha_str: str) -> datetime | None:
    formatos = ("%Y-%m-%d", "%d/%m/%Y")
    
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            continue
    
    return None