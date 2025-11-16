"""
ファイル名: candlestick.py
目的     : ローソク足チャート画像を生成する
概要     : mplfinance を利用して移動平均線付きのチャートを描画し、BytesIO で返却する
入力     : df(pandas.DataFrame), title(str)
出力     : BytesIO: 画像バッファ
"""

from io import BytesIO

import mplfinance as mpf
import matplotlib.pyplot as plt
import pandas as pd


def create_candlestick_image(df: pd.DataFrame, title: str) -> BytesIO:
    """ローソク足と移動平均線を描画して画像バッファを返す。"""
    if df.empty or len(df) < 3:
        raise ValueError("不十分な株価データのためチャートを描画できません。")

    mc = mpf.make_marketcolors(up="red", down="blue")
    style = mpf.make_mpf_style(marketcolors=mc, base_mpf_style="yahoo")

    add_plots = []
    for col, color in [("SMA5", "orange"), ("SMA25", "blue"), ("SMA75", "green")]:
        series = df.get(col)
        if series is not None and not series.dropna().empty:
            add_plots.append(mpf.make_addplot(series, color=color))

    fig, _ = mpf.plot(
        df,
        type="candle",
        style=style,
        volume=True,
        title=title,
        show_nontrading=False,
        addplot=add_plots if add_plots else None,
        returnfig=True,
    )

    img = BytesIO()
    fig.savefig(img, format="png", bbox_inches="tight")
    img.seek(0)
    plt.close(fig)
    return img
