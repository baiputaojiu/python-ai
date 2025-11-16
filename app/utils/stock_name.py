"""
ファイル名: stock_name.py
目的     : 銘柄情報から日本語名を優先して抽出する
概要     : yfinance の info 辞書を確認し、日本語が含まれる候補を優先的に返す
入力     : info(dict): yfinance から取得した銘柄情報
出力     : str: 表示に利用する銘柄名
"""

import re


def _prefer_japanese_name(info: dict) -> str:
    """日本語の表示名があれば優先して返す。"""
    if not isinstance(info, dict):
        return "N/A"

    candidates = [
        info.get("shortName"),
        info.get("longName"),
        info.get("displayName"),
        info.get("name"),
    ]

    for candidate in candidates:
        if candidate and re.search(r"[ぁ-んァ-ン一-龥]", candidate):
            return candidate

    for candidate in candidates:
        if candidate:
            return candidate

    return "N/A"
