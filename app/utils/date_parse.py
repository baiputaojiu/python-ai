"""
ファイル名: date_parse.py
目的     : 決算予定日や権利付き最終日のテキスト解析を担う
概要     : 日付文字列の正規化、ラベルの後ろから日付を推定、GPT 応答からの抽出を実施する
入力     : content(str): GPT などから返る決算情報テキスト
出力     : dict: quarter_dates / rights_date を含む辞書
"""

import json
import re
from datetime import datetime

import pandas as pd


def _to_iso_date(value):
    """pandas / 配列形式の日時を ISO 形式へ揃える。"""
    if value in (None, "", "NaT"):
        return None

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    elif isinstance(value, (pd.Series, pd.Index)):
        if len(value) == 0:
            return None
        value = value.iloc[0] if hasattr(value, "iloc") else value[0]

    if value in (None, "", "NaT"):
        return None

    if isinstance(value, pd.Timestamp):
        ts = value
    elif isinstance(value, (int, float)):
        ts = pd.to_datetime(value, unit="s", utc=True, errors="coerce")
    else:
        ts = pd.to_datetime(str(value), utc=True, errors="coerce")

    if pd.isna(ts):
        return None

    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(None)

    return ts.strftime("%Y-%m-%d")


def _parse_date_text(text: str):
    """日付らしき文字列を ISO 形式へ整形する。"""
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    # 全角→半角変換と記号統一を先に行う
    translate_table = str.maketrans(
        {
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "／": "/",
            "－": "-",
            "―": "-",
            "ー": "-",
            "．": ".",
        }
    )
    text = text.translate(translate_table)
    text = text.replace("年", "/").replace("月", "/").replace("日", "")
    text = text.replace("：", ":")

    def _match_to_iso(match_obj):
        year, month, day = match_obj.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    for sep in ["-", "/", "."]:
        pattern = rf"(\d{{4}})\s*{sep}\s*(\d{{1,2}})\s*{sep}\s*(\d{{1,2}})"
        match = re.search(pattern, text)
        if match:
            iso = _match_to_iso(match)
            if iso:
                return iso

    match = re.search(r"(\d{4})\s+(\d{1,2})\s+(\d{1,2})", text)
    if match:
        iso = _match_to_iso(match)
        if iso:
            return iso

    match = re.search(r"(\d{4})(\d{2})(\d{2})", text)
    if match:
        iso = _match_to_iso(match)
        if iso:
            return iso

    return None


def _extract_date_after_label(content: str, label: str):
    """label の後に続く日付候補を抽出する。"""
    lines = content.splitlines()
    pattern = re.compile(rf"{label}\s*(?:[：:]\s*)?(.*)", re.IGNORECASE)
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        match = pattern.search(line)
        if match:
            remainder = match.group(1).strip()
            if remainder:
                parsed = _parse_date_text(remainder)
                if parsed:
                    return parsed
            if idx + 1 < len(lines):
                parsed = _parse_date_text(lines[idx + 1])
                if parsed:
                    return parsed

    return None


def _extract_event_dates(content: str):
    """GPT 応答のテキストから四半期予定と権利日付を取り出す。"""
    content = (content or "").strip()
    quarter_labels = ["第1四半期", "第2四半期", "第3四半期", "通期"]
    quarter_dates = {}
    rights_date = None

    if not content:
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}

    parts = [p.strip() for p in content.split(",") if p.strip()]
    if len(parts) >= 5:
        for label, value in zip(quarter_labels, parts[:4]):
            quarter_dates[label] = value
        rights_date = parts[4]
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}

    try:
        parsed = json.loads(content)
        quarter_dates = parsed.get("quarter_dates") or {}
        rights_date = parsed.get("rights_date")
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}
    except Exception:
        pass

    for label in quarter_labels:
        extracted = _extract_date_after_label(content, f"{label}決算")
        if extracted:
            quarter_dates[label] = extracted
    rights_date = _extract_date_after_label(content, "権利付き最終日")
    if rights_date is None:
        match = re.search(r"権利付き最終日\s*[:：]?\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            rights_date = match.group(1)

    return {"quarter_dates": quarter_dates, "rights_date": rights_date}
