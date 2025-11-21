import json
from pathlib import Path
from typing import Optional

try:
    from schemas.bounds import MapCanvasBounds
except Exception:
    from backend.schemas.bounds import MapCanvasBounds


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "bounds"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_bounds(upload_id: str, bounds: MapCanvasBounds) -> None:
    fp = DATA_DIR / f"{upload_id}.json"
    with fp.open("w", encoding="utf-8") as f:
        json.dump(bounds.model_dump(), f)


def get_bounds(upload_id: str) -> Optional[MapCanvasBounds]:
    fp = DATA_DIR / f"{upload_id}.json"
    if not fp.exists():
        return None
    with fp.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return MapCanvasBounds(**payload)


