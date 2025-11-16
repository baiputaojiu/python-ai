import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from tkinter import Tk, filedialog, messagebox


# ----------------------------------------
# 株価取得関数（1か月のデータを取得）
# ----------------------------------------
def fetch_stock_info(code: str):
    code = code.strip()

    if code.isdigit():
        code = code.zfill(4)

    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)

    # 1ヶ月分のデータを取得
    data = ticker.history(period="1mo", interval="1d")

    if data.empty:
        return None

    # 最新日と前日データ
    latest = data.iloc[-1]
    prev = data.iloc[-2] if len(data) >= 2 else None

    info = ticker.get_info()
    name = info.get("shortName", "N/A")

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
# ポップアップ表示
# ----------------------------------------
def show_info_popup(result):
    root = Tk()
    root.withdraw()

    latest = result["latest"]
    diff = result["diff"]
    diff_percent = result["diff_percent"]

    msg = (
        f"【{result['code']} | {result['name']}】\n\n"
        f"始値：{latest['Open']:.2f} 円\n"
        f"高値：{latest['High']:.2f} 円\n"
        f"安値：{latest['Low']:.2f} 円\n"
        f"終値：{latest['Close']:.2f} 円\n"
        f"出来高：{int(latest['Volume']):,}\n\n"
    )

    if diff is not None:
        sign = "▲" if diff >= 0 else "▼"
        msg += f"前日比：{sign}{diff:.2f} 円（{diff_percent:.2f}%）\n"
    else:
        msg += "前日比：データなし\n"

    messagebox.showinfo("株価情報", msg)


# ----------------------------------------
# ローソク足チャート（出来高対応・複数同時表示）
# ----------------------------------------
def show_candlestick_chart(result):
    df = result["data"]
    code = result["code"]
    name = result["name"]

    # ★★ 重要：mplfinance に描画を任せる（最も安定）
    mpf.plot(
        df,
        type="candle",
        style="yahoo",
        volume=True,
        title=f"{code} {name}（直近1ヶ月のローソク足）",
        show_nontrading=False
    )

    # 複数チャート同時表示のため block=False
    plt.show(block=False)


# ----------------------------------------
# CSV 保存
# ----------------------------------------
def save_csv_dialog(result):
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="CSV を保存するフォルダを選択してください")

    if folder:
        filename = f"{folder}/{result['code']}_1month.csv"
        result["data"].to_csv(filename)
        messagebox.showinfo("保存完了", f"CSV を保存しました：\n{filename}")
    else:
        messagebox.showinfo("キャンセル", "保存をキャンセルしました。")


# ----------------------------------------
# メイン
# ----------------------------------------
def main():
    print("=== 株価取得アプリ（グラフ & ポップアップ対応） ===")
    print("複数入力可：7203, 6758, 9984 など\n")

    while True:
        user_input = input("銘柄コード（終了:q）：").strip()

        if user_input.lower() == "q":
            print("終了します。")
            break

        codes = [c.strip() for c in user_input.split(",") if c.strip()]

        for code in codes:
            result = fetch_stock_info(code)

            if result is None:
                print(f"[{code}] データ取得失敗\n")
                continue

            # 1. ポップアップ表示
            show_info_popup(result)

            # 2. 複数チャート同時に表示
            show_candlestick_chart(result)

            # 3. CSV 保存
            save = input("CSV を保存しますか？ (y/n)：").lower()
            if save == "y":
                save_csv_dialog(result)


if __name__ == "__main__":
    main()
