"""
ファイル名: code_detect.py
目的     : OCR 結果のテキストから銘柄コードを抽出する
概要     : 正規表現で 4 桁の数字や 4 文字の英数字を検出し、正規化して返す
入力     : text(str): OCR で抽出したテキスト
出力     : list[str]: 抽出・正規化済みの銘柄コード
"""

import re

from app.utils.normalize import _normalize_code

STOCK_CODE_PATTERN = re.compile(r"\b(?:\d{4}|[0-9A-Z]{4})\b")
LOOSE_STOCK_CODE_PATTERN = re.compile(r"(?:\d{4}|[0-9A-Z]{4})")


def extract_stock_codes_from_text(text: str):
    """OCR 文字列に含まれる銘柄コードらしき文字列を抽出して正規化する。"""
    if not text:
        return []

    uppercase_text = text.upper()
    cleaned_text = re.sub(r"[\s\u3000]", "", uppercase_text)

    candidates = list(STOCK_CODE_PATTERN.findall(uppercase_text))
    if cleaned_text:
        candidates.extend(LOOSE_STOCK_CODE_PATTERN.findall(cleaned_text))

    codes = []
    seen = set()
    for raw in candidates:
        normalized = _normalize_code(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            codes.append(normalized)
    return codes
