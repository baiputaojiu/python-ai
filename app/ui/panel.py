"""
ファイル名: panel.py
目的     : 単一銘柄の情報パネルを描画する
概要     : 株価メトリクス・チャート・決算イベント情報の表示をまとめて行う
入力     : code(str), period(str), period_label(str), header_period(str), show_events(bool), event_mode(str)
出力     : なし（Streamlit へ描画）
"""

from datetime import datetime, timedelta

import streamlit as st

from app.charts.candlestick import create_candlestick_image
from app.services.events_openai import CACHE_ONLY_MODE, get_events_info
from app.services.stock_fetch import fetch_stock_info
from app.utils.yahoo_links import get_forum_url


def render_stock_panel(
    code: str,
    period: str,
    period_label: str,
    header_period: str,
    show_events: bool,
    event_mode: str,
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

    forum_url = get_forum_url(result["code"])
    st.markdown(
        f"[Yahoo!ファイナンスの掲示板を開く]({forum_url})",
        unsafe_allow_html=False,
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
        except Exception as e:  # pragma: no cover - UIのみ
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
        events = None
        if events_cache:
            events = events_cache.get(result["code"])

        if events is None:
            fallback_mode = event_mode if show_events else CACHE_ONLY_MODE
            events = get_events_info(result["code"], mode=fallback_mode)

        quarter_dates = events.get("quarter_dates") or {}
        quarter_events = events.get("quarter_events") or {}
        rights_event = events.get("rights_event")
        rights_date = events.get("rights_date")
        raw_response = events.get("raw_response")
        error_message = events.get("error")
        last_updated = events.get("last_updated")
        source_label = "キャッシュ" if events.get("from_cache") else "AI検索"

        today = datetime.now().date()
        two_week_limit = today + timedelta(days=14)
        one_month_limit = today + timedelta(days=30)

        def _parse_iso(date_str):
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                return None

        upcoming_two_week = []
        upcoming_one_month = []
        for label, meta in quarter_events.items():
            iso = meta.get("date")
            dt = _parse_iso(iso)
            if not dt or dt < today:
                continue
            if dt <= two_week_limit:
                upcoming_two_week.append((label, meta))
            elif dt <= one_month_limit:
                upcoming_one_month.append((label, meta))

        rights_two_week = None
        rights_one_month = None
        if rights_event and rights_event.get("date"):
            dt = _parse_iso(rights_event.get("date"))
            if dt and dt >= today:
                if dt <= two_week_limit:
                    rights_two_week = rights_event
                elif dt <= one_month_limit:
                    rights_one_month = rights_event

        def _format_alert(label, meta):
            date_text = meta.get("date_text") or meta.get("date") or "情報なし"
            kind = meta.get("kind")
            if kind:
                return f"{label}: {date_text}（{kind}）"
            return f"{label}: {date_text}"

        alert_messages = []
        if upcoming_two_week:
            msg = " / ".join(_format_alert(label, meta) for label, meta in upcoming_two_week)
            alert_messages.append(("warning", f"⚠️ 2週間以内に決算発表予定日があります: {msg}"))
        if rights_two_week:
            text = rights_two_week.get("date_text") or rights_two_week.get("date") or "情報なし"
            alert_messages.append(
                ("warning", f"⚠️ 2週間以内に権利付き最終日があります: {text}")
            )
        if upcoming_one_month:
            msg = " / ".join(_format_alert(label, meta) for label, meta in upcoming_one_month)
            alert_messages.append(("info", f"ℹ️ 1か月以内に決算発表予定日があります: {msg}"))
        if rights_one_month:
            text = rights_one_month.get("date_text") or rights_one_month.get("date") or "情報なし"
            alert_messages.append(
                ("info", f"ℹ️ 1か月以内に権利付き最終日があります: {text}")
            )

        for level, message in alert_messages:
            if level == "warning":
                st.warning(message)
            else:
                st.info(message)

        st.markdown("### 📅 決算予定日")
        order = ["第1四半期", "第2四半期", "第3四半期", "通期"]
        for label in order:
            meta = quarter_events.get(label)
            if meta:
                date_text = meta.get("date_text") or meta.get("date") or "情報なし"
                kind = meta.get("kind") or "情報不明"
                url = meta.get("source_url")
                if url:
                    url_text = f"[{url}]({url})"
                else:
                    url_text = "出典不明"
                st.markdown(f"{label}: {date_text}（{kind}, {url_text}）")
            else:
                value = quarter_dates.get(label) or "情報なし"
                st.write(f"{label}: {value}")

        st.markdown("### 🎯 権利付き最終日")
        if rights_event:
            date_text = rights_event.get("date_text") or rights_event.get("date") or "情報なし"
            url = rights_event.get("source_url")
            if url:
                url_text = f"[{url}]({url})"
            else:
                url_text = ""
            if url_text:
                st.markdown(f"{date_text}（{url_text}）")
            else:
                st.write(date_text)
        else:
            st.write(rights_date or "情報なし")

        if last_updated:
            st.caption(f"最終更新日: {last_updated}（{source_label}）")
        else:
            st.caption(f"最終更新日: --（{source_label}）")

        if not events.get("quarter_dates") and not events.get("rights_date"):
            st.info("キャッシュされた情報が無い場合は、AI検索をオンにして最新情報を取得してください。")

        with st.expander("GPTレスポンス（デバッグ用途）"):
            if error_message:
                st.write(f"エラー: {error_message}")
            st.code(raw_response or "レスポンスなし", language="json")

    st.markdown("</div>", unsafe_allow_html=True)
