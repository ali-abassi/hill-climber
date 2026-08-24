"""Small intentionally incomplete parser used by the public smoke benchmark."""

UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(value: str) -> int:
    """Convert one integer plus one unit into seconds."""
    if not isinstance(value, str) or len(value) < 2:
        raise ValueError("duration must be an integer followed by h, m, or s")
    try:
        return int(value[:-1]) * UNIT_SECONDS[value[-1]]
    except (KeyError, ValueError) as error:
        raise ValueError("invalid duration") from error
