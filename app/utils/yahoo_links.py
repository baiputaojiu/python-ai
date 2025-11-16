"""
ファイル名: yahoo_links.py
目的     : Yahoo!ファイナンス関連のリンク生成を共通化する
概要     : 銘柄コードを正規化し、掲示板 (/forum) ページの URL を返す
入力     : code(str): 銘柄コード
出力     : str: 掲示板 URL
"""

from app.utils.normalize import _normalize_code


def get_forum_url(code: str) -> str:
    """銘柄コードを正規化して Yahoo!掲示板の URL を返す。"""
    normalized = _normalize_code(code)
    return f"https://finance.yahoo.co.jp/quote/{normalized}.T/forum"
