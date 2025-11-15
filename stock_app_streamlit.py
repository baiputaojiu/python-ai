import os
import json
import re
import textwrap
from datetime import datetime

import streamlit as st
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib import font_manager
from io import BytesIO
import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _configure_matplotlib_font():
    preferred_fonts = [
        "Yu Gothic",
        "YuGothic",
        "Meiryo",
        "MS Gothic",
        "Hiragino Sans",
        "Noto Sans CJK JP",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font in preferred_fonts:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"


_configure_matplotlib_font()


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
    content = (content or "").strip()
    quarter_labels = ["第1四半期", "第2四半期", "第3四半期", "通期"]
    quarter_dates = {}
    rights_date = None

    if not content:
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}

    # Try comma-separated values first
    parts = [p.strip() for p in content.split(",") if p.strip()]
    if len(parts) >= 5:
        for label, value in zip(quarter_labels, parts[:4]):
            quarter_dates[label] = value
        rights_date = parts[4]
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}

    # Fallback: try JSON
    try:
        parsed = json.loads(content)
        quarter_dates = parsed.get("quarter_dates") or {}
        rights_date = parsed.get("rights_date")
        return {"quarter_dates": quarter_dates, "rights_date": rights_date}
    except Exception:
        pass

    # Fallback: try sentence parsing looking for labels
    for label in quarter_labels:
        extracted = _extract_date_after_label(content, f"{label}決算")
        if extracted:
            quarter_dates[label] = extracted
    rights_date = _extract_date_after_label(content, "権利付き最終日")
    if rights_date is None:
        match = re.search(r"権利付き最終日\s*[：:]\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            rights_date = match.group(1)

    return {"quarter_dates": quarter_dates, "rights_date": rights_date}


def get_events_by_openai(code: str):
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return {
            "quarter_dates": {},
            "rights_date": None,
            "raw_response": None,
            "error": "OpenAI API unavailable",
        }

    client = OpenAI()
    prompt = textwrap.dedent(
        f"""
        日本株 {code} について、最新または最も確からしい決算発表予定と権利付き最終日を信頼できる日本語ソースや過去実績から推定して調べてください。
        回答は「第1四半期・第2四半期・第3四半期・通期・権利付き最終日」の順に、半角カンマ区切りで 5 つの日付文字列のみを返してください。
        例: 2025年8月上旬,2025年11月上旬,2026年2月上旬,2026年5月上旬,2026-03-27
        厳密な日付が不明でも「2025年8月上旬」「2026年2月中旬」のように幅を持たせた表現を必ず記載してください。
        情報が全く得られない場合のみ「情報未取得」と記載してください。それ以外の文章・JSON・説明は一切出力しないでください。
        """
    ).strip()

    result = {"quarter_dates": {}, "rights_date": None, "raw_response": None, "error": None}
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
        choice = response.choices[0]
        message_content = choice.message.content
        if isinstance(message_content, list):
            parts = []
            for block in message_content:
                if isinstance(block, dict) and block.get("type") == "output_text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            content = "".join(parts).strip()
        else:
            content = (message_content or "").strip()

        if not content:
            result["raw_response"] = response.model_dump_json(indent=2, ensure_ascii=False)
            result["error"] = "OpenAI response contained no text content."
        else:
            result["raw_response"] = content
            extracted = _extract_event_dates(content)
            result["quarter_dates"] = extracted.get("quarter_dates") or {}
            result["rights_date"] = extracted.get("rights_date")
    except Exception as exc:
        result["error"] = str(exc)

    return result

def get_events_info(code: str):
    normalized = code.strip()
    if normalized.isdigit():
        normalized = normalized.zfill(4)
    symbol = f"{normalized}.T"

    ai_result = get_events_by_openai(normalized)
    quarter_dates = ai_result.get("quarter_dates") or {}
    rights_date = ai_result.get("rights_date")

    return {
        "quarter_dates": quarter_dates,
        "rights_date": rights_date,
        "raw_response": ai_result.get("raw_response"),
        "error": ai_result.get("error"),
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
st.set_page_config(
    page_title="株価表示アプリ",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stock-card {
        background-color: #f8f9fb;
        border: 1px solid #e5e8ef;
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 24px;
        box-shadow: 0 2px 4px rgba(18, 38, 63, 0.06);
    }
    .stock-card h2 {
        margin-top: 0;
    }
    .metric-row {
        display: flex;
        gap: 12px;
    }
    .metric-row > div {
        flex: 1;
    }
    .chart-wrapper {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 株価表示アプリ (Streamlit 強化版)")

period_map = {
    "1か月": "1mo",
    "3か月": "3mo",
    "6か月": "6mo",
    "1年": "1y",
    "5年": "5y",
}
period_label_short = {
    "1か月": "1M",
    "3か月": "3M",
    "6か月": "6M",
    "1年": "1Y",
    "5年": "5Y",
}

period_label = st.selectbox("期間を選択してください", list(period_map.keys()))
period = period_map[period_label]
header_period = period_label_short.get(period_label, period_label)

st.write(f"選択中の期間: **{period_label} ({period})**")
show_events = st.checkbox(
    "決算予定日・権利付き最終日も表示する（AI検索を含むためコストが発生します）",
    value=False,
)

st.markdown("---")
st.write("銘柄の指定方法:")
st.write("- 銘柄コード（例: 7203）")
st.write("- 複数コード（例: 7203, 6758, 9984）")
st.write("- 銘柄名（例: トヨタ） → 自動で検索")

keyword = st.text_input("銘柄コード または 銘柄名（カンマ区切り可）")


def render_stock_panel(code: str):
    result = fetch_stock_info(code, period=period)

    if result is None:
        st.error(f"[{code}] の株価データを取得できませんでした。")
        return

    st.markdown("<div class='stock-card'>", unsafe_allow_html=True)
    st.markdown(
        f"### {result['code']} | {result['name']}  (Period: {header_period})"
    )

    latest = result["latest"]
    diff = result["diff"]
    diff_percent = result["diff_percent"]

    col_metrics = st.columns(3)
    with col_metrics[0]:
        st.metric("終値", f"{latest['Close']:.2f} 円")
        st.write(f"始値: {latest['Open']:.2f} 円")
    with col_metrics[1]:
        st.metric("高値", f"{latest['High']:.2f} 円")
        st.write(f"安値: {latest['Low']:.2f} 円")
    with col_metrics[2]:
        if diff is not None and diff_percent is not None:
            st.metric("前日比", f"{diff:+.2f} 円", f"{diff_percent:+.2f}%")
        else:
            st.metric("前日比", "--", "--")
        st.write(f"出来高: {int(latest['Volume']):,}")

    content_cols = st.columns([3, 2])
    with content_cols[0]:
        try:
            img = create_candlestick_image(
                result["data"], f"{result['code']} {result['name']} ({period_label})"
            )
            st.image(img, width="stretch")
        except Exception as e:
            st.error(f"チャート生成に失敗しました: {e}")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        csv = result["data"].to_csv().encode("utf-8")
        st.download_button(
            label="📥 CSV をダウンロード",
            data=csv,
            file_name=f"{result['code']}_{period}.csv",
            mime="text/csv",
        )

    with content_cols[1]:
        if show_events:
            with st.spinner("決算予定日と権利付き最終日を取得中..."):
                events = get_events_info(result["code"])

            quarter_dates = events.get("quarter_dates") or {}
            rights_event = events.get("rights_date")
            raw_response = events.get("raw_response")
            error_message = events.get("error")

            st.markdown("### 📅 決算予定日 (ChatGPT)")
            order = ["第1四半期", "第2四半期", "第3四半期", "通期"]
            for label in order:
                value = quarter_dates.get(label) or "情報なし"
                st.write(f"{label}: {value}")

            st.markdown("### 🎯 権利付き最終日 (ChatGPT)")
            st.write(rights_event or "情報なし")

            with st.expander("GPTレスポンス（デバッグ）"):
                if error_message:
                    st.write(f"エラー: {error_message}")
                st.code(raw_response or "レスポンスなし", language="json")
        else:
            st.caption("決算予定日・権利付き最終日の取得は現在オフになっています。")

    st.markdown("</div>", unsafe_allow_html=True)


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

        st.write("🔍 一致した候補:")
        for code, name in matches:
            st.write(f"- {code} : {name}")

        first_code, first_name = matches[0]
        st.info(f"最初の候補 {first_code} : {first_name} を使用します。")
        codes = [first_code]

    if not codes:
        st.warning("表示する銘柄がありません。")
        st.stop()

    cols_per_row = min(3, len(codes)) if len(codes) > 1 else 1

    for i in range(0, len(codes), cols_per_row):
        row_codes = codes[i:i + cols_per_row]
        columns = st.columns(len(row_codes))
        for column, code in zip(columns, row_codes):
            with column:
                render_stock_panel(code)
