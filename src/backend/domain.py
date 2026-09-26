import json
from pathlib import Path
from types import SimpleNamespace
CONFIG=json.loads((Path(__file__).resolve().parents[1]/"domain.json").read_text(encoding="utf-8"))
globals().update({key:SimpleNamespace(**values) for key,values in CONFIG.items()})
