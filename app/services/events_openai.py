"""
ファイル名: events_openai.py
目的     : OpenAI API を利用して決算予定日と権利付き最終日を取得する
概要     : 単体リクエスト・複数リクエストの双方を実装し、Streamlit UI へ辞書形式で返す
入力     : code(str) もしくは codes(list[str])
出力     : dict: quarter_dates / rights_date / raw_response / error を含む辞書
"""

import os
import textwrap

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - オプション機能
    OpenAI = None

from app.utils.date_parse import _extract_event_dates
from app.utils.normalize import _normalize_code


def _format_openai_missing():
    return {
        "quarter_dates": {},
        "rights_date": None,
        "raw_response": None,
        "error": "OpenAI API unavailable",
    }


def _collect_text_content(message_content):
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


def get_events_by_openai(code: str):
    """1 銘柄分の決算予定日を OpenAI へ問い合わせる。"""
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return _format_openai_missing()

    client = OpenAI()
    prompt = textwrap.dedent(
        f"""
        日本株 {code} について、最新または最も確からしい決算発表予定と権利付き最終日を信頼できる日本語ソースや過去実績から推定して調べてください。
        回答は「第1四半期・第2四半期・第3四半期・通期・権利付き最終日」を順番に、半角カンマ区切りで 5 つの日付文字列のみを返してください。
        例: 2025年8月上旬,2025年11月上旬,2026年2月上旬,2026年5月上旬,2026-03-27
        厳密な日付が不明でも、「2025年8月上旬」「2026年2月中旬」のように幅を持たせた表現を必ず記載してください。
        情報が全く得られない場合のみ「情報未取得」と記載してください。それ以外の表や JSON や説明を一切出力しないでください。
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
        content = _collect_text_content(choice.message.content)

        if not content:
            result["raw_response"] = response.model_dump_json(indent=2, ensure_ascii=False)
            result["error"] = "OpenAI response contained no text content."
        else:
            result["raw_response"] = content
            extracted = _extract_event_dates(content)
            result["quarter_dates"] = extracted.get("quarter_dates") or {}
            result["rights_date"] = extracted.get("rights_date")
    except Exception as exc:  # pragma: no cover - API 呼び出しエラー
        result["error"] = str(exc)

    return result


def get_events_by_openai_batch(codes):
    """複数銘柄を一括で問い合わせし、行単位のレスポンスを解析する。"""
    normalized_codes = []
    seen = set()
    for code in codes:
        norm = _normalize_code(code)
        if not norm or norm in seen:
            continue
        normalized_codes.append(norm)
        seen.add(norm)

    if not normalized_codes:
        return {}

    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return {norm: _format_openai_missing() for norm in normalized_codes}

    client = OpenAI()
    code_lines = "\n".join(f"- {c}" for c in normalized_codes)
    prompt = textwrap.dedent(
        f"""
        以下の日本株コードそれぞれについて、最新または最も確からしい決算発表予定と権利付き最終日を信頼できる日本語ソースや過去実績から推定して調べてください。
        各コードの回答は「第1四半期・第2四半期・第3四半期・通期・権利付き最終日」の順で日付を必ず示し、厳密な日付が不明でも「2025年8月上旬」「2026年2月中旬」のように幅を持たせた表現を記載してください。
        情報が全く得られない場合のみ「情報未取得」と記載してください。それ以外の表や JSON や説明を一切出力しないでください。

        出力形式: 1 行につき銘柄のみ
        7203: 2025年8月上旬,2025年11月上旬,2026年2月上旬,2026年5月上旬,2026-03-27
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
            norm: {
                "quarter_dates": {},
                "rights_date": None,
                "raw_response": None,
                "error": str(exc),
            }
            for norm in normalized_codes
        }

    raw_response = response.model_dump_json(indent=2, ensure_ascii=False)
    content = _collect_text_content(response.choices[0].message.content)
    if not content:
        return {
            norm: {
                "quarter_dates": {},
                "rights_date": None,
                "raw_response": raw_response,
                "error": "OpenAI response contained no text content.",
            }
            for norm in normalized_codes
        }

    quarter_labels = ["第1四半期", "第2四半期", "第3四半期", "通期"]
    results = {
        norm: {
            "quarter_dates": {},
            "rights_date": None,
            "raw_response": raw_response,
            "error": f"{norm} のデータを読み取れませんでした。",
        }
        for norm in normalized_codes
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

        quarter_dates = {label: value for label, value in zip(quarter_labels, values[:4])}
        rights_date = values[4]

        results[code_part] = {
            "quarter_dates": quarter_dates,
            "rights_date": rights_date,
            "raw_response": raw_response,
            "error": None
            if quarter_dates or rights_date
            else f"{code_part} のデータを読み取れませんでした。",
        }

    return results


def get_events_info(code: str):
    """単一銘柄用ヘルパー。OpenAI からの情報を正規化する。"""
    normalized = _normalize_code(code)
    ai_result = get_events_by_openai(normalized)
    quarter_dates = ai_result.get("quarter_dates") or {}
    rights_date = ai_result.get("rights_date")

    return {
        "quarter_dates": quarter_dates,
        "rights_date": rights_date,
        "raw_response": ai_result.get("raw_response"),
        "error": ai_result.get("error"),
    }


def fetch_events_info_for_codes(codes):
    """複数コードに対してイベント情報をまとめて返す。"""
    normalized_codes = [_normalize_code(code) for code in codes if _normalize_code(code)]
    if not normalized_codes:
        return {}

    if len(normalized_codes) == 1:
        code = normalized_codes[0]
        return {code: get_events_info(code)}

    batch_results = get_events_by_openai_batch(normalized_codes)

    for code in normalized_codes:
        if code not in batch_results:
            batch_results[code] = get_events_info(code)

    return batch_results
