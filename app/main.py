"""
ファイル名: main.py
目的     : Streamlit アプリ全体の UI を構築する
概要     : 期間選択や OCR 入力、株価取得ボタンと結果表示の制御を行う
入力     : ユーザー操作 (テキスト入力・画像アップロード)
出力     : なし（Streamlit への描画のみ）
"""

import pandas as pd
import streamlit as st

from app.config.fonts import _configure_matplotlib_font
from app.config.tesseract import _configure_tesseract_command
from app.services.events_openai import (
    ALWAYS_AI_MODE,
    CACHE_FIRST_MODE,
    CACHE_ONLY_MODE,
)
from app.services.stock_fetch import fetch_stock_info
from app.ui.results import display_stock_results
from app.utils.code_detect import extract_stock_codes_from_text
from app.utils.ocr import extract_text_from_image
from app.utils.stock_search import search_stock_code

_configure_matplotlib_font()
_configure_tesseract_command()


def run():
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
    manual_show_events = st.checkbox(
        "決算予定日・権利付き最終日も表示する（AI検索を含むためコストが発生します）",
        value=False,
    )

    mode_items = [
        ("キャッシュだけ見る", CACHE_ONLY_MODE),
        ("1か月以内のキャッシュがあればAIスキップ、それ以外はAI検索＋キャッシュ更新", CACHE_FIRST_MODE),
        ("常にAI検索してキャッシュも更新", ALWAYS_AI_MODE),
    ]
    mode_labels = [label for label, _ in mode_items]
    selected_label = st.selectbox("決算予定日・権利付き最終日の取得方法", mode_labels, index=1)
    event_mode = dict(mode_items)[selected_label]
    show_events = manual_show_events or (event_mode != CACHE_ONLY_MODE)

    st.markdown("---")
    st.write("銘柄の入力方法")
    st.write("- 銘柄コード（例: 7203）")
    st.write("- 複数コード（例: 7203, 6758, 9984）")
    st.write("- 銘柄名（例: トヨタ）なら自動で検索")

    keyword_input = st.text_input("銘柄コードまたは 銘柄名（カンマ区切り可）")
    keyword = keyword_input

    uploaded_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
    ocr_text = ""
    ocr_codes = []
    ocr_valid_codes = []
    ocr_result_cache = {}
    if uploaded_image is not None:
        try:
            ocr_text = extract_text_from_image(uploaded_image)
            st.text_area("OCR結果", value=ocr_text or "※ テキストが検出されませんでした ※", height=200)
            ocr_codes = extract_stock_codes_from_text(ocr_text)
            if ocr_codes:
                st.success(f"OCRで抽出された銘柄コード候補: {', '.join(ocr_codes)}")

                skipped_from_ocr = []
                with st.spinner("OCRで検出した銘柄コードから株価データ取得可否を確認しています..."):
                    for code in ocr_codes:
                        result = fetch_stock_info(code, period=period)
                        if result is None:
                            skipped_from_ocr.append(code)
                            continue

                        normalized_code = result["code"]
                        if normalized_code in ocr_result_cache:
                            continue

                        ocr_valid_codes.append(normalized_code)
                        ocr_result_cache[normalized_code] = result

                if ocr_valid_codes:
                    table_rows = [
                        {"コード": code, "銘柄名": ocr_result_cache[code]["name"]}
                        for code in ocr_valid_codes
                    ]
                    st.write("🔎 OCRで株価データ取得が確認できた銘柄一覧")
                    st.table(pd.DataFrame(table_rows))
                    st.info("上記の銘柄について株価を取得するには、下の「株価を取得」ボタンを押してください。")
                else:
                    st.warning("OCRで読み取った銘柄から有効な株価データが得られませんでした。")

                if skipped_from_ocr:
                    st.warning(
                        "以下のコードは株価データを取得できなかったため除外しました: "
                        + ", ".join(skipped_from_ocr)
                    )
            else:
                st.warning("OCRで銘柄コードを検出できませんでした。")
        except Exception as ocr_exc:
            st.error(f"OCR処理中にエラーが発生しました: {ocr_exc}")

    if st.button("株価を取得"):
        codes = []
        preloaded = None
        spinner_message = None

        if ocr_valid_codes:
            codes = ocr_valid_codes
            preloaded = ocr_result_cache
            spinner_message = "OCRで抽出した銘柄の決算予定日 (ChatGPT) をまとめて取得中..."
        else:
            if not keyword.strip():
                st.warning("銘柄コードまたは銘柄名を入力してください。")
                st.stop()

            keyword = keyword.strip()

            if "," in keyword:
                codes = [c.strip() for c in keyword.split(",") if c.strip()]
            elif keyword.isdigit():
                codes = [keyword]
            else:
                matches = search_stock_code(keyword)
                if not matches:
                    st.error("該当する銘柄が見つかりませんでした。")
                    st.stop()

                st.write("🔍 一致した候補")
                for code, name in matches:
                    st.write(f"- {code} : {name}")

                first_code, first_name = matches[0]
                st.info(f"最初の候補 {first_code} : {first_name} を使用します。")
                codes = [first_code]

        display_stock_results(
            codes,
            period=period,
            period_label=period_label,
            header_period=header_period,
            show_events=show_events,
            event_mode=event_mode,
            spinner_label=spinner_message,
            preloaded_results=preloaded,
        )
