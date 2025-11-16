"""
ファイル名: normalize.py
目的     : 銘柄コードの文字列を正規化する
概要     : 前後の空白除去やゼロ埋めを行い、Streamlit UI 全体で利用できる形に整える
入力     : code(str): 生の銘柄コード文字列
出力     : str: 正規化済みの銘柄コード
"""


def _normalize_code(code: str) -> str:
    """銘柄コードの空白除去およびゼロ埋めを行う。"""
    normalized = (code or "").strip()
    if not normalized:
        return ""
    if normalized.isdigit():
        normalized = normalized.zfill(4)
    return normalized
