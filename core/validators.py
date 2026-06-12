import re

from django.core.exceptions import ValidationError

_SEASON_RE = re.compile(r"^(\d{4})/(\d{4})$")


def validate_season_format(value):
    """Stagione canonica: AAAA/AAAA con secondo anno = primo+1 (es. 2025/2026)."""
    match = _SEASON_RE.match(value or "")
    if not match:
        raise ValidationError(
            "Formato stagione non valido: usa AAAA/AAAA (es. 2025/2026)."
        )
    year1, year2 = int(match.group(1)), int(match.group(2))
    if year2 != year1 + 1:
        raise ValidationError(
            "La seconda annata deve essere la prima +1 (es. 2025/2026)."
        )
