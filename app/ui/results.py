"""
ファイル名: results.py
目的     : 複数銘柄の検索結果をまとめて表示する
概要     : 銘柄コードの重複排除、株価データ取得、イベント情報・UI ボタン描画を担当
入力     : codes(list[str]), period/label 情報, show_events(bool) など
出力     : なし（Streamlit へ描画）
"""

import json
from typing import Dict, List, Optional
from uuid import uuid4

import streamlit as st
from streamlit.components.v1 import html

from app.services.events_openai import (
    ALWAYS_AI_MODE,
    CACHE_FIRST_MODE,
    CACHE_ONLY_MODE,
    fetch_events_info_for_codes,
)
from app.services.stock_fetch import fetch_stock_info
from app.ui.panel import render_stock_panel
from app.utils.yahoo_links import get_forum_url


def display_stock_results(
    codes: List[str],
    period: str,
    period_label: str,
    header_period: str,
    show_events: bool,
    event_mode: str,
    spinner_label: Optional[str] = None,
    preloaded_results: Optional[Dict[str, dict]] = None,
) -> None:
    """複数銘柄の株価結果を描画する。"""
    unique_codes: List[str] = []
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
    valid_codes: List[str] = []
    result_cache: Dict[str, dict] = {}
    skipped_codes: List[str] = []
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

    st.caption(
        "ブラウザのポップアップブロックを解除していないと、掲示板タブが開かない場合があります。"
    )

    yahoo_urls = [get_forum_url(code) for code in valid_codes]
    urls_json = json.dumps(yahoo_urls)
    function_id = uuid4().hex
    open_all_html = f"""
    <button class="open-yahoo-boards" onclick="openAllYahooBoards_{function_id}()">
        全銘柄の掲示板を別タブで一気に開く
    </button>
    <script>
    function openAllYahooBoards_{function_id}() {{
        const urls = {urls_json};
        for (const url of urls) {{
            window.open(url, '_blank');
        }}
    }}
    </script>
    """
    html(open_all_html, height=80)

    active_mode = event_mode if show_events else CACHE_ONLY_MODE

    if show_events:
        events_cache = {}
        message = spinner_label or "選択した銘柄の決算予定日 (ChatGPT) をまとめて取得中..."
        with st.spinner(message):
            events_cache = fetch_events_info_for_codes(valid_codes, active_mode)
    else:
        events_cache = fetch_events_info_for_codes(valid_codes, active_mode)

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
                    event_mode=active_mode,
                    events_cache=events_cache,
                    preloaded_result=result_cache.get(code),
                )
