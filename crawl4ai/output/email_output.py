"""Email output with helper utilities."""

import json
from typing import Any, List, Union

from . import EmailOutput as _EmailOutput


class EmailOutput(_EmailOutput):
    """Extended EmailOutput with parsing utilities."""

    @staticmethod
    def _parse_extracted(raw: Union[str, list]) -> List[Any]:
        """Parse extracted content from various formats into a list."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
                return [parsed]
            except (json.JSONDecodeError, TypeError):
                return [raw.strip()] if raw.strip() else []
        return []
