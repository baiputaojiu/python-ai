import os
import re
import textwrap
from datetime import datetime

import streamlit as st
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from io import BytesIO
import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ----------------------------------------
# 銘柄名 → コード検索（Yahoo Finance 検索API使用）
# ----------------------------------------
def search_stock_code(keyword: str, max_results: int = 5):
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


# ----------------------------------------
# 株価データ取得（期間選択 & 移動平均付き）
# ----------------------------------------
def fetch_stock_info(code: str, period: str = "1mo"):
    code = code.strip()

    if code.isdigit():
        code = code.zfill(4)

    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)

    data = ticker.history(period=period, interval="1d")

    # データ不足対策
    if data.empty or len(data) < 3:
        return None

    # 必須列チェック
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(data.columns):
        return None

    # 銘柄名
    try:
        info = ticker.get_info()
        name = info.get("shortName", "N/A")
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

    # 移動平均線
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


# ----------------------------------------
# 決算予定日・権利付き最終日 補完ロジック
# ----------------------------------------
def _to_iso_date(value):
    if value in (None, "", "NaT"):
        return None

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    elif isinstance(value, (pd.Series, pd.Index)):
        if len(value) == 0:
            return None
        value = value.iloc[0] if hasattr(value, "iloc") else value[0]

    if value in (None, "", "NaT"):
        return None

    if isinstance(value, pd.Timestamp):
        ts = value
    elif isinstance(value, (int, float)):
        ts = pd.to_datetime(value, unit="s", utc=True, errors="coerce")
    else:
        ts = pd.to_datetime(str(value), utc=True, errors="coerce")

    if pd.isna(ts):
        return None

    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(None)

    return ts.strftime("%Y-%m-%d")


def _parse_date_text(text: str):
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    # 全角 → 半角、記号統一
    translate_table = str.maketrans({
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
        "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
        "／": "/", "－": "-", "―": "-", "ー": "-", "．": ".",
    })
    text = text.translate(translate_table)
    text = text.replace("年", "/").replace("月", "/").replace("日", "")
    text = text.replace("：", ":")

    def _match_to_iso(match_obj):
        year, month, day = match_obj.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    # yyyy-mm-dd / yyyy/mm/dd / yyyy.mm.dd
    for sep in ["-", "/", "."]:
        pattern = rf"(\d{{4}})\s*{sep}\s*(\d{{1,2}})\s*{sep}\s*(\d{{1,2}})"
        match = re.search(pattern, text)
        if match:
            iso = _match_to_iso(match)
            if iso:
                return iso

    # yyyy mm dd（スペース区切りなど）
    match = re.search(r"(\d{4})\s+(\d{1,2})\s+(\d{1,2})", text)
    if match:
        iso = _match_to_iso(match)
        if iso:
            return iso

    # yyyymmdd
    match = re.search(r"(\d{4})(\d{2})(\d{2})", text)
    if match:
        iso = _match_to_iso(match)
        if iso:
            return iso

    return None


def _extract_date_after_label(content: str, label: str):
    lines = content.splitlines()
    pattern = re.compile(rf"{label}\s*(?:[：:]\s*)?(.*)", re.IGNORECASE)
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        match = pattern.search(line)
        if match:
            remainder = match.group(1).strip()
            if remainder:
                parsed = _parse_date_text(remainder)
                if parsed:
                    return parsed
            # 次行に日付があるケース
            if idx + 1 < len(lines):
                parsed = _parse_date_text(lines[idx + 1])
                if parsed:
                    return parsed

    return None


def _extract_event_dates(content: str):
    earnings_date = _extract_date_after_label(content, "決算予定日")
    rights_date = _extract_date_after_label(content, "権利付き最終日")

    # フォールバック：単純な ISO 形式
    if earnings_date is None:
        match = re.search(r"決算予定日\s*[：:]\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            earnings_date = match.group(1)
    if rights_date is None:
        match = re.search(r"権利付き最終日\s*[：:]\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            rights_date = match.group(1)

    return {"earnings_date": earnings_date, "rights_date": rights_date}


def get_events_by_openai(code: str):
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return {"earnings_date": None, "rights_date": None, "earnings_summary": None}

    client = OpenAI()
    prompt = textwrap.dedent(
        f"""
        日本株 {code} の決算発表予定と権利付き最終日をインターネット検索して調べてください。
        必ず複数の信頼できる日本の金融サイト（Yahoo!ファイナンス、株探、SBI、楽天証券、IR情報など）を参照し、
        最新期の予定と根拠となる公開情報（正式な日付や予定時期）を確認してください。

        出力形式（絶対に変更しないこと）:
        - **第1四半期決算**：テキスト
        - **第2四半期決算**：テキスト
        - **第3四半期決算**：テキスト
        - **通期決算（本決算）**：テキスト

        各テキストには「YYYY年M月D日」「YYYY年M月上旬」などの形で予定時期や日時を含め、
        補足の説明や根拠サイト（例: global.toyota）を括弧付きで示してください。
        その後に改行して以下の行を付けてください:
        権利付き最終日: YYYY-MM-DD
        """
    ).strip()

    result = {"earnings_date": None, "rights_date": None, "earnings_summary": None}
    try:
        response = client.chat.completions.create(
            model="gpt-4o-search-preview",
            web_search_options={
                "user_location": {
                    "type": "approximate",
                    "approximate": {
                        "country": "JP",
                        "city": "Tokyo",
                        "region": "Tokyo",
                    },
                },
            },
            messages=[
                {
                    "role": "system",
                    "content": "あなたは金融情報を調査するアシスタントです。信頼できる日本語ソースを検索し、最新の決算予定と権利付き最終日を整理して回答してください。",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        if content:
            result["earnings_summary"] = content
            extracted = _extract_event_dates(content)
            if extracted.get("earnings_date"):
                result["earnings_date"] = extracted["earnings_date"]
            if extracted.get("rights_date"):
                result["rights_date"] = extracted["rights_date"]
    except Exception:
        pass

    return result

def get_events_info(code: str):
    normalized = code.strip()
    if normalized.isdigit():
        normalized = normalized.zfill(4)
    symbol = f"{normalized}.T"

    rights_date = None
    rights_source = None

    try:
        ticker = yf.Ticker(symbol)
    except Exception:
        ticker = None

    if ticker is not None:
        try:
            cal = ticker.get_calendar()
            if cal is not None and not cal.empty:
                cal_series = cal["Value"] if "Value" in cal.columns else cal.iloc[:, 0]
                rights_date = _to_iso_date(cal_series.get("Ex-Dividend Date"))
                if rights_date:
                    rights_source = "yahoo"
        except Exception:
            pass

        if rights_date is None:
            try:
                info = ticker.get_info()
                rights_date = _to_iso_date(info.get("exDividendDate"))
                if rights_date:
                    rights_source = "yahoo"
            except Exception:
                pass

    ai_result = get_events_by_openai(normalized)
    earnings_summary = ai_result.get("earnings_summary")
    earnings_date = ai_result.get("earnings_date")
    sources = {"earnings": "openai"}

    if rights_date is None and ai_result.get("rights_date"):
        rights_date = ai_result["rights_date"]
        rights_source = "openai"

    if rights_source:
        sources["rights"] = rights_source

    return {
        "earnings_summary": earnings_summary,
        "earnings_date": earnings_date,
        "rights_date": rights_date,
        "sources": sources,
    }


# ----------------------------------------
# ローソク足 + 移動平均線の画像生成
# ----------------------------------------
def create_candlestick_image(df: pd.DataFrame, title: str) -> BytesIO:

    if df.empty or len(df) < 3:
        raise ValueError("不十分な株価データのためチャートを描画できません。")

    mc = mpf.make_marketcolors(up="red", down="blue")
    s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style="yahoo")

    add_plots = []
    for col, color in [("SMA5", "orange"), ("SMA25", "blue"), ("SMA75", "green")]:
        series = df.get(col)
        if series is not None and not series.dropna().empty:
            add_plots.append(mpf.make_addplot(series, color=color))

    fig, _ = mpf.plot(
        df,
        type="candle",
        style=s,
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


# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.title("📈 株価表示アプリ（強化版 Streamlit）")

period_map = {
    "1ヶ月": "1mo",
    "3ヶ月": "3mo",
    "6ヶ月": "6mo",
    "1年": "1y",
    "5年": "5y",
}

period_label = st.selectbox("期間を選択してください", list(period_map.keys()))
period = period_map[period_label]

st.write(f"選択中の期間: **{period_label} ({period})**")

st.markdown("---")

st.write("銘柄の指定方法：")
st.write("- **銘柄コード（例: 7203）**")
st.write("- **複数コード（例: 7203, 6758, 9984）**")
st.write("- **銘柄名（例: トヨタ） → 自動で検索**")

keyword = st.text_input("銘柄コード または 銘柄名")

if st.button("株価を取得"):

    if not keyword.strip():
        st.warning("銘柄コードまたは銘柄名を入力してください。")
        st.stop()

    keyword = keyword.strip()

    codes = []

    if "," in keyword:
        codes = [c.strip() for c in keyword.split(",") if c.strip()]
    elif keyword.isdigit():
        codes = [keyword]
    else:
        matches = search_stock_code(keyword)
        if not matches:
            st.error("該当する銘柄が見つかりませんでした。")
            st.stop()

        st.write("🔍 一致した候補：")
        for code, name in matches:
            st.write(f"- {code} : {name}")

        first_code, first_name = matches[0]
        st.info(f"最初の候補 **{first_code} : {first_name}** を使用します。")
        codes = [first_code]

    tabs = st.tabs([f"{code} の分析" for code in codes])

    for tab, code in zip(tabs, codes):
        with tab:

            result = fetch_stock_info(code, period=period)

            if result is None:
                st.error(f"[{code}] の株価データを取得できませんでした。")
                continue

            st.subheader(f"【{result['code']} | {result['name']}】（期間：{period_label}）")

            latest = result["latest"]
            diff = result["diff"]
            diff_percent = result["diff_percent"]

            st.write(f"**始値：** {latest['Open']:.2f} 円")
            st.write(f"**高値：** {latest['High']:.2f} 円")
            st.write(f"**安値：** {latest['Low']:.2f} 円")
            st.write(f"**終値：** {latest['Close']:.2f} 円")
            st.write(f"**出来高：** {int(latest['Volume']):,}")

            if diff is not None and diff_percent is not None:
                sign = "▲" if diff >= 0 else "▼"
                st.write(f"**前日比：** {sign}{diff:.2f} 円 ({diff_percent:.2f}%)")
            else:
                st.write("前日比：データなし")

            st.markdown("### 📅 決算予定日・権利付き最終日（最新情報）")
            with st.spinner("最新の日付情報を取得しています..."):
                events = get_events_info(result["code"])

            earnings_summary = events.get("earnings_summary")
            earnings_event = events.get("earnings_date")
            rights_event = events.get("rights_date")
            sources = events.get("sources") or {}
            source_map = {
                "openai": "ChatGPT（インターネット検索補完）",
                "yahoo": "Yahoo Finance（yfinance）",
            }

            st.markdown("**決算予定スケジュール（ChatGPT調査）**")
            if earnings_summary:
                st.markdown(earnings_summary)
            elif earnings_event:
                st.write(f"決算予定日：{earnings_event}")
            else:
                st.write("決算予定：情報なし")
            st.caption(f"取得元（決算）：{source_map.get(sources.get('earnings'), '情報なし')}")

            st.write(f"**権利付き最終日：** {rights_event or '情報なし'}")
            rights_source_label = source_map.get(sources.get("rights"), "情報なし")
            st.caption(f"取得元（権利付き最終日）：{rights_source_label}")

            # チャート（安全な try/except）
            try:
                img = create_candlestick_image(
                    result["data"],
                    f"{result['code']} {result['name']}（{period_label}）",
                )
                st.image(img)

            except Exception as e:
                st.error(f"チャート生成に失敗しました：{e}")
                continue

            csv = result["data"].to_csv().encode("utf-8")
            st.download_button(
                label="📥 CSV をダウンロード",
                data=csv,
                file_name=f"{result['code']}_{period}.csv",
                mime="text/csv",
            )
