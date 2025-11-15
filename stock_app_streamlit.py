import streamlit as st
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from io import BytesIO


# ----------------------------------------
# 株価データ取得
# ----------------------------------------
def fetch_stock_info(code: str):
    code = code.strip()
    if code.isdigit():
        code = code.zfill(4)

    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)

    data = ticker.history(period="1mo", interval="1d")
    if data.empty:
        return None

    info = ticker.get_info()
    name = info.get("shortName", "N/A")

    latest = data.iloc[-1]
    prev = data.iloc[-2] if len(data) >= 2 else None

    diff = None
    diff_percent = None
    if prev is not None:
        diff = latest["Close"] - prev["Close"]
        diff_percent = diff / prev["Close"] * 100

    return {
        "code": code,
        "name": name,
        "data": data,
        "latest": latest,
        "diff": diff,
        "diff_percent": diff_percent,
    }


# ----------------------------------------
# ローソク足チャートを画像として返す
# ----------------------------------------
def create_candlestick_image(df, title):
    fig, ax = mpf.plot(
        df,
        type="candle",
        style="yahoo",
        volume=True,
        title=title,
        show_nontrading=False,
        returnfig=True
    )

    img = BytesIO()
    fig.savefig(img, format="png", bbox_inches="tight")
    img.seek(0)
    plt.close(fig)
    return img


# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.title("📈 株価表示アプリ（Streamlit版）")

codes_input = st.text_input(
    "銘柄コード（複数の場合：7203, 6758 のようにカンマ区切り）"
)

if st.button("株価を取得"):
    if not codes_input:
        st.warning("銘柄コードを入力してください")
    else:
        codes = [c.strip() for c in codes_input.split(",") if c.strip()]

        for code in codes:
            result = fetch_stock_info(code)

            if result is None:
                st.error(f"[{code}] の株価データを取得できませんでした。")
                continue

            st.subheader(f"【{result['code']} | {result['name']}】")

            latest = result["latest"]
            diff = result["diff"]

            # 情報表示
            st.write(f"**始値：** {latest['Open']:.2f} 円")
            st.write(f"**高値：** {latest['High']:.2f} 円")
            st.write(f"**安値：** {latest['Low']:.2f} 円")
            st.write(f"**終値：** {latest['Close']:.2f} 円")
            st.write(f"**出来高：** {int(latest['Volume']):,}")

            if diff is not None:
                sign = "▲" if diff >= 0 else "▼"
                st.write(f"**前日比：** {sign}{diff:.2f} 円 ({result['diff_percent']:.2f}%)")
            else:
                st.write("前日比：データなし")

            # チャート画像生成して表示
            img = create_candlestick_image(
                result["data"],
                f"{result['code']} {result['name']}（直近1ヶ月）"
            )
            st.image(img)

            # CSV ダウンロード
            csv = result["data"].to_csv().encode("utf-8")
            st.download_button(
                label="📥 CSV をダウンロード",
                data=csv,
                file_name=f"{result['code']}_1month.csv",
                mime="text/csv"
            )
