"""Constants for ČEZ Distribuce PND."""

DOMAIN = "cez_pnd"

CONF_ELECTROMETER = "electrometer"
CONF_DATE_FROM = "date_from"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # minut
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 1440

# Systémová sestava „00 Profil spotřeby a výroby + Rv“ – obsahuje řady +A i -A
ASSEMBLY = -1003

# Sloupce tabulky statistik
COL_TOTAL_INTERVAL = "1007"  # Celkem v intervalu
COL_COMPLETENESS = "1009"  # Úplnost dat

# Formát uložení data „od“ (stejný, jaký vrací DateTimeSelector)
DATE_FMT = "%Y-%m-%d %H:%M:%S"
