"""
ファイル名: results.py
目的     : 複数銘柄の検索結果をまとめて表示する
概要     : 銘柄コードの重複排除、株価データ取得、イベントのまとめ取得、パネル描画を担当
入力     : codes(list[str]) など UI からの指定
出力     : なし（Streamlit へ描画）
"""

import json
import streamlit as st
from streamlit.components.v1 import html

from app.services.events_openai import fetch_events_info_for_codes
from app.services.stock_fetch import fetch_stock_info
from app.ui.panel import render_stock_panel


def display_stock_results(
    codes,
    period,
    period_label,
    header_period,
    show_events,
    spinner_label=None,
    preloaded_results=None,
):
    """複数銘柄の株価結果を描画する。"""
    unique_codes = []
    seen = set()
    for code in codes:
        cleaned = code.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_codes.append(cleaned)

    if not unique_codes:
        st.warning("表示する銘柄がありません。")
        return

    preloaded_results = preloaded_results or {}
    valid_codes = []
    result_cache = {}
    skipped_codes = []
    for code in unique_codes:
        preloaded = preloaded_results.get(code)
        if preloaded is not None:
            result = preloaded
        else:
            result = fetch_stock_info(code, period=period)

        if result is None:
            skipped_codes.append(code)
            continue
        valid_codes.append(code)
        result_cache[code] = result

    if skipped_codes:
        st.warning(
            f"株価データを取得できなかったためスキップしたコード: {', '.join(skipped_codes)}"
        )

    if not valid_codes:
        st.warning("有効な銘柄コードがありませんでした。")
        return

    # 全銘柄分の Yahoo!ファイナンス掲示板をまとめて開くボタン。
    # 公式サイトを新しいタブで開くだけなので、スクレイピング等の禁止事項には抵触しない。
    yahoo_urls = [f"https://finance.yahoo.co.jp/quote/{code}.T/forum" for code in valid_codes]
    urls_json = json.dumps(yahoo_urls)
    open_all_html = f"""
    <button onclick="openAllYahooBoards()">全銘柄の掲示板を別タブで一気に開く</button>
    <script>
    function openAllYahooBoards() {{
        const urls = {urls_json};
        for (const url of urls) {{
            window.open(url, '_blank');
        }}
    }}
    </script>
    """
    html(open_all_html, height=70)

    events_cache = {}
    if show_events:
        message = spinner_label or "選択した銘柄の決算予定日 (ChatGPT) をまとめて取得中..."
        with st.spinner(message):
            events_cache = fetch_events_info_for_codes(valid_codes)

    cols_per_row = min(3, len(valid_codes)) if len(valid_codes) > 1 else 1
    for i in range(0, len(valid_codes), cols_per_row):
        row_codes = valid_codes[i : i + cols_per_row]
        columns = st.columns(len(row_codes))
        for column, code in zip(columns, row_codes):
            with column:
                render_stock_panel(
                    code,
                    period=period,
                    period_label=period_label,
                    header_period=header_period,
                    show_events=show_events,
                    events_cache=events_cache if show_events else None,
                    preloaded_result=result_cache.get(code),
                )
