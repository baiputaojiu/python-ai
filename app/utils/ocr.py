"""
ファイル名: ocr.py
目的     : アップロードされた画像からテキストを抽出する
概要     : Streamlit のアップロードファイルを PIL で開き、pytesseract で OCR を実行する
入力     : uploaded_file: Streamlit の UploadedFile オブジェクト
出力     : str: OCR で検出したテキスト
"""

import pytesseract
from PIL import Image


def extract_text_from_image(uploaded_file) -> str:
    """アップロードされた画像から OCR でテキストを抽出する。"""
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)
    image = image.convert("RGB")
    text = pytesseract.image_to_string(image, lang="jpn")
    uploaded_file.seek(0)
    return text.strip()
