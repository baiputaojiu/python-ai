"""
ファイル名: events_cache.py
目的     : 決算予定日・権利付き最終日のキャッシュ管理
概要     : JSON ファイルを通して銘柄ごとのイベント情報と最終更新日を読み書きする
入力     : 銘柄コード、イベント情報辞書
出力     : イベント情報辞書（last_updated / from_cache を含む）
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from app.utils.normalize import _normalize_code

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_FILE = DATA_DIR / "events_cache.json"
MAX_CACHE_AGE_DAYS = 183  # 約6か月


def _load_cache() -> Dict[str, dict]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: Dict[str, dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached_events(code: str, max_age_days: int = MAX_CACHE_AGE_DAYS) -> Optional[dict]:
    """指定コードのキャッシュを取得。一定期間を超えていれば None を返す。"""
    normalized = _normalize_code(code)
    cache = _load_cache()
    entry = cache.get(normalized)
    if not entry:
        return None

    last_updated = entry.get("last_updated")
    if not last_updated:
        return None

    try:
        updated_dt = datetime.fromisoformat(last_updated)
    except ValueError:
        return None

    # UTC を想定。タイムゾーン情報がなければ UTC とみなす。
    if updated_dt.tzinfo is None:
        updated_dt = updated_dt.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - updated_dt > timedelta(days=max_age_days):
        return None

    result = dict(entry)
    result["from_cache"] = True
    return result


def set_cached_events(code: str, events: dict) -> dict:
    """イベント情報をキャッシュへ保存し、last_updated を設定して返す。"""
    normalized = _normalize_code(code)
    cache = _load_cache()

    payload = {
        "quarter_dates": events.get("quarter_dates") or {},
        "rights_date": events.get("rights_date"),
        "raw_response": events.get("raw_response"),
        "error": events.get("error"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    cache[normalized] = payload
    _save_cache(cache)

    payload["from_cache"] = False
    return payload

