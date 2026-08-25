from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SeasonWindow:
    name: str
    start: date
    end: date
    authority: str
    version: str


def season_for(day: date, windows: list[SeasonWindow]) -> SeasonWindow | None:
    matches = [window for window in windows if window.start <= day <= window.end]
    if len(matches) > 1:
        raise ValueError("Approved season windows overlap")
    return matches[0] if matches else None
