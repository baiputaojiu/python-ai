import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------------------
# 株価取得関数
# ----------------------------------------
def fetch_stock_info(code: str):
    """
    銘柄コード（例：7203）から株価情報を取得する。
    返り値：dict または None
    """
    code = code.strip()

    if code.isdigit():
        code = code.zfill(4)

    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)

    # 最近2日分（前日比を計算するため）
    data = ticker.history(period="2d")

    if data.empty:
        return None

    # 銘柄名（shortName）を取得
    info = ticker.get_info()
    name = info.get("shortName", "N/A")

    # 最新データ（当日）
    latest = data.iloc[-1]

    # 1日前のデータ（前日値）
    if len(data) >= 2:
        prev = data.iloc[-2]
        diff = latest["Close"] - prev["Close"]
        diff_percent = diff / prev["Close"] * 100
    else:
        diff = None
        diff_percent = None

    return {
        "code": code,
        "name": name,
        "open": latest["Open"],
        "high": latest["High"],
        "low": latest["Low"],
        "close": latest["Close"],
        "volume": latest["Volume"],
        "diff": diff,
        "diff_percent": diff_percent,
        "history": data,
    }


# ----------------------------------------
# チャート生成
# ----------------------------------------
def draw_chart(df: pd.DataFrame, code: str, name: str):
    plt.figure(figsize=(10, 4))
    plt.plot(df.index, df["Close"], marker="o")
    plt.title(f"{code} {name}（終値チャート）")
    plt.xlabel("Date")
    plt.ylabel("Close (JPY)")
    plt.grid(True)
    plt.tight_layout()
    plt.show()


# ----------------------------------------
# メイン処理
# ----------------------------------------
def main():
    print("=== 株価取得アプリ（拡張版） ===")
    print("複数入力可能：7203, 6758, 9984 など")
    print("終了する場合は q\n")

    while True:
        user_input = input("銘柄コード（複数可・カンマ区切り）：").strip()

        if user_input.lower() in {"q", "quit", "exit"}:
            print("終了します。")
            break

        # カンマ入力対応
        codes = [c.strip() for c in user_input.split(",") if c.strip()]

        for code in codes:
            result = fetch_stock_info(code)

            if result is None:
                print(f"[{code}] 株価を取得できませんでした\n")
                continue

            print("\n-------------------------")
            print(f"{result['code']} | {result['name']}")
            print("-------------------------")
            print(f"始値：{result['open']:.2f} 円")
            print(f"高値：{result['high']:.2f} 円")
            print(f"安値：{result['low']:.2f} 円")
            print(f"終値：{result['close']:.2f} 円")
            print(f"出来高：{result['volume']:,}")

            if result["diff"] is not None:
                sign = "▲" if result["diff"] >= 0 else "▼"
                print(f"前日比：{sign}{result['diff']:.2f} 円 ({result['diff_percent']:.2f}%)")
            else:
                print("前日比：データ不足")

            # チャート表示
            draw_chart(result["history"], result["code"], result["name"])

            # CSV 保存オプション
            save_csv = input("CSV に保存しますか？（y/n）：").lower()
            if save_csv == "y":
                # --- 追加：保存フォルダをエクスプローラで選択 ---
                from tkinter import Tk, filedialog
                root = Tk()
                root.withdraw()  # tkinter のウィンドウを隠す

                folder = filedialog.askdirectory(title="CSV を保存するフォルダを選択してください")

                if folder:
                    filename = f"{folder}/{result['code']}_history.csv"
                    result["history"].to_csv(filename)
                    print(f"→ CSVとして保存しました：{filename}\n")
                else:
                    print("保存をキャンセルしました。\n")



if __name__ == "__main__":
    main()
