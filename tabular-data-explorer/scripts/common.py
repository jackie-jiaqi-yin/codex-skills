#!/usr/bin/env python3

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def json_ready(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_ready(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if value is pd.NaT:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(path: str | Path, payload) -> None:
    target = Path(path)
    target.write_text(json.dumps(json_ready(payload), indent=2, ensure_ascii=False) + "\n")


def read_json(path: str | Path):
    return json.loads(Path(path).read_text())


def as_display(value, limit: int = 80) -> str:
    if value is None or value is pd.NA:
        return ""
    if value is pd.NaT:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"
