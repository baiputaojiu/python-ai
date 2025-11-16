"""
ファイル名: stock_fetch.py
目的     : yfinance を用いた株価データ取得を行う
概要     : 指定した期間の株価データと移動平均を取得し、UI で使いやすい形に整形する
入力     : code(str), period(str)
出力     : dict: 銘柄コード・名称・最新値・変化率等を含む辞書
"""

import pandas as pd
import yfinance as yf

from app.utils.stock_name import _prefer_japanese_name


def fetch_stock_info(code: str, period: str = "1mo"):
    """銘柄コードから株価データを取得し、メトリクスを組み立てる。"""
    code = code.strip()

    if code.isdigit():
        code = code.zfill(4)

    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)

    data = ticker.history(period=period, interval="1d")

    if data.empty or len(data) < 3:
        return None

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(data.columns):
        return None

    try:
        info = ticker.get_info()
        name = _prefer_japanese_name(info)
    except Exception:
        name = "N/A"

    latest = data.iloc[-1]
    prev = data.iloc[-2] if len(data) >= 2 else None

    diff = None
    diff_percent = None
    if prev is not None:
        diff = latest["Close"] - prev["Close"]
        if prev["Close"] != 0:
            diff_percent = diff / prev["Close"] * 100

    data["SMA5"] = data["Close"].rolling(5).mean()
    data["SMA25"] = data["Close"].rolling(25).mean()
    data["SMA75"] = data["Close"].rolling(75).mean()

    return {
        "code": code,
        "name": name,
        "data": data,
        "latest": latest,
        "diff": diff,
        "diff_percent": diff_percent,
    }
