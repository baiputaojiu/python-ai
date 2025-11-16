"""
ファイル名: ocr.py
目的     : アップロードされた画像からテキストを抽出する
概要     : Streamlit のアップロードファイルを PIL で開き、pytesseract で OCR を実行する
入力     : uploaded_file: Streamlit の UploadedFile オブジェクト
出力     : str: OCR で検出したテキスト
"""

import io
import os

import pytesseract
from PIL import Image

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

BACKEND_TESSERACT = "tesseract"
BACKEND_OPENAI = "openai_vision"
BACKEND_NONE = "none"

ENABLE_VISION = os.getenv("ENABLE_VISION_OCR", "").lower() in {"1", "true", "yes"}


def _has_tesseract() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _has_openai() -> bool:
    return ENABLE_VISION and OpenAI is not None and bool(os.getenv("OPENAI_API_KEY"))


def _detect_backend() -> str:
    if _has_tesseract():
        return BACKEND_TESSERACT
    if _has_openai():
        return BACKEND_OPENAI
    return BACKEND_NONE


OCR_BACKEND = _detect_backend()


def extract_text_from_image(uploaded_file) -> str:
    """アップロードされた画像から OCR でテキストを抽出する。"""
    if OCR_BACKEND == BACKEND_TESSERACT:
        return _extract_with_tesseract(uploaded_file)
    if OCR_BACKEND == BACKEND_OPENAI:
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

    client = OpenAI()
    uploaded_file.seek(0)
    image = Image.open(uploaded_file).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    image_bytes = buffer.read()
    uploaded_file.seek(0)

    prompt = (
        "画像に含まれる日本語テキストをそのまま抽出してください。"
        "説明を加えず、検出したテキストのみをそのまま返してください。"
    )

    response = client.responses.create(
        model=os.getenv("OPENAI_OCR_MODEL", "gpt-4o-mini"),
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_bytes": image_bytes,
                    },
                ],
            }
        ],
    )

    output_text = []
    for choice in response.output:
        if choice.type == "message":
            for segment in choice.message.content:
                if segment.type == "output_text":
                    output_text.append(segment.text)
    if not output_text:
        raise RuntimeError("OpenAI Visionの出力を取得できませんでした。")
    return "\n".join(output_text).strip()
