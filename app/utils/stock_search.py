"""
ファイル名: stock_search.py
目的     : Yahoo Finance の検索 API を用いた銘柄コード検索
概要     : キーワードから候補を検索し、国内銘柄のコードと名称を返却する
入力     : keyword(str): 検索キーワード
出力     : list[tuple[str, str]]: (銘柄コード, 銘柄名) の上限 max_results 個
"""

import requests
import streamlit as st


def search_stock_code(keyword: str, max_results: int = 5):
    """Yahoo Finance の検索 API で銘柄を探し、国内銘柄のみ返す。"""
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {
        "q": keyword,
        "lang": "ja-JP",
        "region": "JP",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.error(f"銘柄検索中にエラーが発生しました: {e}")
        return []

    candidates = []
    for item in data.get("quotes", []):
        symbol = item.get("symbol", "")
        name = item.get("shortname") or item.get("longname") or ""
        if symbol.endswith(".T"):
            code = symbol.replace(".T", "")
            candidates.append((code, name))
            if len(candidates) >= max_results:
                break

    return candidates
