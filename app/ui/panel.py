"""
ファイル名: panel.py
目的     : 単一銘柄の情報パネルを描画する
概要     : 株価メトリクス・チャート・決算イベント情報の表示をまとめて行う
入力     : code(str), period/label 情報、イベントキャッシュ等
出力     : なし（Streamlit へ描画）
"""

import streamlit as st

from app.charts.candlestick import create_candlestick_image
from app.services.events_openai import get_events_info
from app.services.stock_fetch import fetch_stock_info


def render_stock_panel(
    code: str,
    period: str,
    period_label: str,
    header_period: str,
    show_events: bool,
    events_cache=None,
    preloaded_result=None,
):
    """1 銘柄のカード UI を描画する。"""
    result = preloaded_result or fetch_stock_info(code, period=period)

    if result is None:
        st.error(f"[{code}] の株価データを取得できませんでした。")
        return

    st.markdown("<div class='stock-card'>", unsafe_allow_html=True)
    st.markdown(f"### {result['code']} | {result['name']}  (Period: {header_period})")

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
            events = None
            if events_cache:
                events = events_cache.get(result["code"])

            if events is None:
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

            with st.expander("GPTレスポンス（デバッグ用途）"):
                if error_message:
                    st.write(f"エラー: {error_message}")
                st.code(raw_response or "レスポンスなし", language="json")
        else:
            st.caption("決算予定日・権利付き最終日の取得は現在オフになっています。")

    st.markdown("</div>", unsafe_allow_html=True)
