from openai import OpenAI
import os

# 環境変数から API キーを取得
API_KEY = os.getenv("OPENAI_API_KEY")

if API_KEY is None:
    raise ValueError("環境変数 OPENAI_API_KEY が設定されていません。")

client = OpenAI(api_key=API_KEY)


# ユーザーの入力に対してWeb検索を含む回答を生成する
def search_and_chat(user_input: str) -> str:
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
                {"role": "user", "content": user_input},
            ],
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"error: {str(e)}"


def main():
    while True:
        user_input = input("質問: ").strip()

        if user_input.lower() in ["quit", "exit", "終了"]:
            print("\n終了します。")
            break

        if not user_input:
            print("質問を入力してください\n")
            continue

        print("\n検索中...\n")
        answer = search_and_chat(user_input)

        print(f"回答:\n{answer}\n")
        print("-" * 50 + "\n")


if __name__ == "__main__":
    main()

