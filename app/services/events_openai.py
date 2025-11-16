"""
ファイル名: events_openai.py
目的     : OpenAI API とキャッシュを組み合わせて決算予定日・権利付き最終日を取得する
概要     : OpenAI への単体／複数問い合わせとレスポンス解析、ローカルキャッシュの保存・読み出しを担当する
入力     : 銘柄コード、取得モード（キャッシュのみ・キャッシュ優先・常にAI）
出力     : quarter_dates / quarter_events / rights_date / rights_event / raw_response 等を含む辞書
"""

from __future__ import annotations

import os
import textwrap
from typing import Dict, List

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - オプション機能
    OpenAI = None

from app.storage.events_cache import get_cached_events, set_cached_events
from app.utils.date_parse import _extract_event_dates
from app.utils.normalize import _normalize_code

CACHE_ONLY_MODE = "cache_only"
CACHE_FIRST_MODE = "cache_first"
ALWAYS_AI_MODE = "always_ai"
RECENT_CACHE_DAYS = 31  # 約1か月


def _format_openai_missing() -> dict:
    return {
        "quarter_dates": {},
        "quarter_events": {},
        "rights_date": None,
        "rights_event": None,
        "raw_response": None,
        "error": "OpenAI API unavailable",
        "last_updated": None,
        "from_cache": False,
    }


def _collect_text_content(message_content) -> str:
    if isinstance(message_content, list):
        parts = []
        for block in message_content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                parts.append(block.get("text", ""))
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return (message_content or "").strip()


def _finalize_result(data: dict, *, from_cache: bool) -> dict:
    return {
        "quarter_dates": data.get("quarter_dates") or {},
        "quarter_events": data.get("quarter_events") or {},
        "rights_date": data.get("rights_date"),
        "rights_event": data.get("rights_event"),
        "raw_response": data.get("raw_response"),
        "error": data.get("error"),
        "last_updated": data.get("last_updated"),
        "from_cache": from_cache,
    }


def _empty_cache_result(message: str) -> dict:
    return {
        "quarter_dates": {},
        "quarter_events": {},
        "rights_date": None,
        "rights_event": None,
        "raw_response": None,
        "error": message,
        "last_updated": None,
        "from_cache": True,
    }


def get_events_by_openai(code: str) -> dict:
    """1 銘柄分の決算予定日を OpenAI へ問い合わせる。"""
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return _format_openai_missing()

    client = OpenAI()
    prompt = textwrap.dedent(
        f"""
        日本株 {code} について、最新または最も確からしい決算発表予定と権利付き最終日を信頼できる日本語ソースや過去実績から推定して調べてください。
        各四半期については、次回の決算発表予定日が分かる場合はその日付を、分からない場合は前回の決算発表日を用いてください。
        回答は「第1四半期・第2四半期・第3四半期・通期・権利付き最終日」を順番に、半角カンマ区切りで 5 個の要素のみを1行で返してください。
        先頭4つの要素は、必ず「2025年8月12日（予定｜https://example.com/ir1）」または「2025年8月12日（前回｜https://example.com/ir2）」のように、
        「日付（予定または前回｜出典URL）」という形式で出力してください。URL は日本語以外で、直前直後に空白を入れないでください。
        最後の要素（権利付き最終日）も同様に、「2026年3月27日（予定｜https://example.com/ir5）」または「2026年3月27日（前回｜https://example.com/ir6）」のように、
        「日付（予定または前回｜出典URL）」という形式で出力してください。権利付き最終日のみ日付だけ、となる形式は使用しないでください。
        例: 2025年8月12日（前回｜https://example.com/ir1）,2025年11月11日（前回｜https://example.com/ir2）,2026年2月4日（予定｜https://example.com/ir3）,2026年5月14日（予定｜https://example.com/ir4）,2026年3月27日（予定｜https://example.com/ir5）
        情報が全く得られない場合のみ「情報未取得」と 1 語だけ出力してください。それ以外の表・JSON・説明文・改行を一切出力しないでください。
        """
    ).strip()

    result = {
        "quarter_dates": {},
        "quarter_events": {},
        "rights_date": None,
        "rights_event": None,
        "raw_response": None,
        "error": None,
    }
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
        content = _collect_text_content(choice.message.content)

        if not content:
            result["raw_response"] = response.model_dump_json(indent=2, ensure_ascii=False)
            result["error"] = "OpenAI response contained no text content."
        else:
            result["raw_response"] = content
            extracted = _extract_event_dates(content)
            result["quarter_dates"] = extracted.get("quarter_dates") or {}
            result["quarter_events"] = extracted.get("quarter_events") or {}
            result["rights_date"] = extracted.get("rights_date")
            result["rights_event"] = extracted.get("rights_event")
    except Exception as exc:  # pragma: no cover - API 呼び出しエラー
        result["error"] = str(exc)

    return result


def get_events_by_openai_batch(codes: List[str]) -> Dict[str, dict]:
    """複数銘柄を一括で問い合わせし、行単位のレスポンスを解析する。"""
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return {code: _format_openai_missing() for code in codes}

    client = OpenAI()
    code_lines = "\n".join(f"- {c}" for c in codes)
    prompt = textwrap.dedent(
        f"""
        以下の日本株コードそれぞれについて、最新または最も確からしい決算発表予定と権利付き最終日を信頼できる日本語ソースや過去実績から推定して調べてください。
        各コードの回答は「第1四半期・第2四半期・第3四半期・通期・権利付き最終日」の順に、半角カンマ区切りで 5 個の要素だけを 1 行で出力してください。
        先頭4つの値は必ず「2025年8月12日（予定｜https://example.com/ir1）」または「2025年8月12日（前回｜https://example.com/ir2）」のように
        「日付（予定または前回｜出典URL）」という形式で出力してください。URL の前後に余分な空白を入れないでください。
        最後の値（権利付き最終日）も、必ず「2026年3月27日（予定｜https://example.com/ir5）」または「2026年3月27日（前回｜https://example.com/ir6）」のように、
        「日付（予定または前回｜出典URL）」という形式で出力してください。
        情報が全く得られない場合のみ「情報未取得」と記載してください。それ以外の表・JSON・説明文・改行を一切出力しないでください。

        出力形式: 1 行につき銘柄のみ
        7203: 2025年8月12日（前回｜https://example.com/ir1）,2025年11月11日（前回｜https://example.com/ir2）,2026年2月4日（予定｜https://example.com/ir3）,2026年5月14日（予定｜https://example.com/ir4）,2026年3月27日（予定｜https://example.com/ir5）
        6758: ...

        対象コード:
        {code_lines}
        """
    ).strip()

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
    except Exception as exc:  # pragma: no cover - API 呼び出し失敗時
        return {
            code: {
                "quarter_dates": {},
                "quarter_events": {},
                "rights_date": None,
                "rights_event": None,
                "raw_response": None,
                "error": str(exc),
            }
            for code in codes
        }

    raw_response = response.model_dump_json(indent=2, ensure_ascii=False)
    content = _collect_text_content(response.choices[0].message.content)
    if not content:
        return {
            code: {
                "quarter_dates": {},
                "quarter_events": {},
                "rights_date": None,
                "rights_event": None,
                "raw_response": raw_response,
                "error": "OpenAI response contained no text content.",
            }
            for code in codes
        }

    results = {
        code: {
            "quarter_dates": {},
            "quarter_events": {},
            "rights_date": None,
            "rights_event": None,
            "raw_response": raw_response,
            "error": f"{code} のデータを読み取れませんでした。",
        }
        for code in codes
    }

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in lines:
        if ":" not in line:
            continue
        code_part, values_part = line.split(":", 1)
        code_part = code_part.strip()
        if code_part not in results:
            continue

        values = [p.strip() for p in values_part.split(",") if p.strip()]
        if len(values) < 5:
            results[code_part]["error"] = f"{code_part} の値が不足しています。"
            continue

        extracted = _extract_event_dates(",".join(values[:5]))
        results[code_part] = {
            "quarter_dates": extracted.get("quarter_dates") or {},
            "quarter_events": extracted.get("quarter_events") or {},
            "rights_date": extracted.get("rights_date"),
            "rights_event": extracted.get("rights_event"),
            "raw_response": raw_response,
            "error": None,
        }

    return results


def _fetch_via_ai(codes: List[str]) -> Dict[str, dict]:
    """指定されたコードを AI で取得してキャッシュへ保存する。"""
    if not codes:
        return {}

    if len(codes) == 1:
        code = codes[0]
        ai_result = get_events_by_openai(code)
        stored = set_cached_events(code, ai_result)
        return {_normalize_code(code): _finalize_result(stored, from_cache=False)}

    batch_results = get_events_by_openai_batch(codes)
    final_results: Dict[str, dict] = {}
    for code in codes:
        ai_result = batch_results.get(code) or _format_openai_missing()
        stored = set_cached_events(code, ai_result)
        final_results[_normalize_code(code)] = _finalize_result(stored, from_cache=False)
    return final_results


def get_events_info(code: str, mode: str, recent_days: int = RECENT_CACHE_DAYS) -> dict:
    """モードに応じてキャッシュ/AI検索を組み合わせて情報を取得。"""
    normalized = _normalize_code(code)
    if not normalized:
        return _empty_cache_result("無効な銘柄コードです。")

    if mode == CACHE_ONLY_MODE:
        cached = get_cached_events(normalized)
        if cached:
            return _finalize_result(cached, from_cache=True)
        return _empty_cache_result("キャッシュが存在しません。")

    if mode == CACHE_FIRST_MODE:
        cached = get_cached_events(normalized, max_age_days=recent_days)
        if cached:
            return _finalize_result(cached, from_cache=True)
        ai_result = get_events_by_openai(normalized)
        stored = set_cached_events(normalized, ai_result)
        return _finalize_result(stored, from_cache=False)

    if mode == ALWAYS_AI_MODE:
        ai_result = get_events_by_openai(normalized)
        stored = set_cached_events(normalized, ai_result)
        return _finalize_result(stored, from_cache=False)

    return _empty_cache_result("不明な取得モードです。")


def fetch_events_info_for_codes(
    codes: List[str],
    mode: str,
    recent_days: int = RECENT_CACHE_DAYS,
) -> Dict[str, dict]:
    """複数コード分のイベント情報をまとめて取得。"""
    normalized_codes: List[str] = []
    seen = set()
    for code in codes:
        norm = _normalize_code(code)
        if not norm or norm in seen:
            continue
        normalized_codes.append(norm)
        seen.add(norm)

    if not normalized_codes:
        return {}

    if mode == CACHE_ONLY_MODE:
        return {code: get_events_info(code, CACHE_ONLY_MODE, recent_days) for code in normalized_codes}

    if mode == CACHE_FIRST_MODE:
        results: Dict[str, dict] = {}
        ai_targets: List[str] = []
        for code in normalized_codes:
            cached = get_cached_events(code, max_age_days=recent_days)
            if cached:
                results[code] = _finalize_result(cached, from_cache=True)
            else:
                ai_targets.append(code)
        if ai_targets:
            results.update(_fetch_via_ai(ai_targets))
        return results

    if mode == ALWAYS_AI_MODE:
        return _fetch_via_ai(normalized_codes)

    return {code: _empty_cache_result("不明な取得モードです。") for code in normalized_codes}
