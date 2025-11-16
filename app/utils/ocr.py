"""
ファイル名: ocr.py
目的     : 画像からテキストを抽出する
概要     : Streamlit のアップロード画像を PIL で読み込み、pytesseract もしくは OpenAI Vision で OCR を行う
入力     : uploaded_file: Streamlit の UploadedFile オブジェクト
出力     : str: OCR で得られたテキスト
"""

import io
import os
from typing import Dict

import pytesseract
from PIL import Image

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

BACKEND_TESSERACT = "tesseract"
BACKEND_OPENAI = "openai_vision"
BACKEND_AUTO = "auto"
BACKEND_NONE = "none"


def _has_tesseract() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _has_openai() -> bool:
    return OpenAI is not None and bool(os.getenv("OPENAI_API_KEY"))


def get_available_ocr_backends() -> Dict[str, bool]:
    return {
        BACKEND_TESSERACT: _has_tesseract(),
        BACKEND_OPENAI: _has_openai(),
    }


def _detect_backend() -> str:
    if _has_tesseract():
        return BACKEND_TESSERACT
    if _has_openai():
        return BACKEND_OPENAI
    return BACKEND_NONE


def extract_text_from_image(uploaded_file, backend: str | None = None) -> str:
    """アップロードされた画像から OCR でテキストを抽出する。"""
    selected_backend = backend or BACKEND_AUTO
    if selected_backend == BACKEND_AUTO:
        selected_backend = _detect_backend()

    if selected_backend == BACKEND_TESSERACT:
        if not _has_tesseract():
            raise RuntimeError("Tesseract OCR が利用できません。")
        return _extract_with_tesseract(uploaded_file)

    if selected_backend == BACKEND_OPENAI:
        if not _has_openai():
            raise RuntimeError("OpenAI Vision OCR が利用できません。")
        return _extract_with_openai(uploaded_file)

    raise RuntimeError("この環境ではOCR機能が利用できません。")


def _extract_with_tesseract(uploaded_file) -> str:
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)
    image = image.convert("RGB")
    text = pytesseract.image_to_string(image, lang="jpn")
    uploaded_file.seek(0)
    return text.strip()


def _extract_with_openai(uploaded_file) -> str:
    if OpenAI is None:
        raise RuntimeError("OpenAIライブラリが利用できません。")
    # NOTE: 現状は Chat Completions API で Vision OCR を実行している。
    # OpenAI の Responses API でも同様の処理は可能で、ケースによっては料金が安くなる場合がある。

    client = OpenAI()
    uploaded_file.seek(0)
    image = Image.open(uploaded_file).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    image_bytes = buffer.read()
    uploaded_file.seek(0)

    prompt = (
        "画像に写っているすべてのテキストを、画面の上から順に抜き出してください。"
        "日本語だけでなく、数字やアルファベット・記号も必ず含めてください。"
        "特に銘柄名の下に表示されている銘柄コード（4桁の数字や英数字）は絶対に省略しないでください。"
        "改行や区切りは画面の並びに従い、説明や要約は書かず、検出したテキストだけをそのまま返してください。"
    )

    import base64

    b64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64_image}"

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_OCR_MODEL", "gpt-4o-mini"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )

    message_content = response.choices[0].message.content
    if isinstance(message_content, list):
        parts = []
        for block in message_content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        text = "".join(parts).strip()
    else:
        text = (message_content or "").strip()

    if not text:
        raise RuntimeError("OpenAI Visionの出力を取得できませんでした。")
    return text
