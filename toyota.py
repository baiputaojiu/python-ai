import requests
from bs4 import BeautifulSoup

def get_toyota_earnings_date():
    url = "https://www.zacks.com/stock/research/TM/earnings-calendar"

    # Zacks は User-Agent を求めるため設定
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception("ページ取得に失敗しました")

    soup = BeautifulSoup(response.text, "html.parser")

    # ページ内の決算予定日が入っている要素を探索
    # 例: <span class="right">Feb 04, 2026</span>
    date_span = soup.select_one("span.right")

    if date_span:
        return date_span.text.strip()

    return "決算日が見つかりませんでした"

# 実行
if __name__ == "__main__":
    try:
        earnings_date = get_toyota_earnings_date()
        print("トヨタの次の決算発表予定日:", earnings_date)
    except Exception as e:
        print("エラー:", e)
