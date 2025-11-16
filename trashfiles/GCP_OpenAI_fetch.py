import os
import requests
import urllib.parse
from openai import OpenAI

# -------------------------------
# 環境変数からキーを読み込み
# -------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GOOGLE_API_KEY or not GOOGLE_CX or not OPENAI_API_KEY:
    raise ValueError("Missing GOOGLE_API_KEY, GOOGLE_CX, or OPENAI_API_KEY.")


client = OpenAI(api_key=OPENAI_API_KEY)


def google_search(query):
    """Googleカスタム検索を実行"""
    url = (
        "https://www.googleapis.com/customsearch/v1?"
        f"key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&q={urllib.parse.quote(query)}"
    )
    return requests.get(url).json()


def ask_gpt_for_quarter_earnings(text, company_label):
    """GPTに決算発表予定日を抽出させる"""

    prompt = f"""
以下はGoogle検索で集めたテキスト断片です。
この中から **{company_label} の決算発表予定日（第１四半期, 第２四半期, 第３四半期, 第４四半期）** を可能な限り抽出してください。

注意事項:
- 「5月上旬」「8月中旬予定」などのあいまいな表現でも可。
- 該当情報がなければ "unknown" とする。
- 複数候補がある場合は最も信頼できるものを1つ選ぶ。

必ず次のJSONフォーマットで回答してください。
{{
  "1Q": "YYYY-MM-DD または '5月上旬' または unknown",
  "2Q": "1Qと同じ形式",
  "3Q": "1Qと同じ形式",
  "4Q": "1Qと同じ形式"
}}

検索テキスト:
{text}
"""

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "あなたは決算発表予定日を抽出するアナリストAIです。"},
            {"role": "user", "content": prompt}
        ]
    )
    return res.choices[0].message.content


def get_company_quarter_earnings(company_query):
    """四半期ごとの決算発表予定日をまとめる"""
    query = f"{company_query} 決算発表日 四半期"
    data = google_search(query)

    if "items" not in data:
        return "検索結果を取得できませんでした。"

    collected = ""
    for item in data["items"]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        collected += f"[{title}]\n{snippet}\n{link}\n\n"

    return ask_gpt_for_quarter_earnings(collected, company_query)


# -------------------------------
# エントリポイント
# -------------------------------
if __name__ == "__main__":
    user_input = input("銘柄コードまたは会社名を入力してください: ").strip()
    if not user_input:
        raise ValueError("銘柄コードまたは会社名の入力が必要です。")

    result = get_company_quarter_earnings(user_input)
    print(result)
