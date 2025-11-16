"""
ファイル名: tesseract.py
目的     : Tesseract OCR の実行パスを設定する
概要     : 環境変数と Windows 既定のパスを順番に確認し、pytesseract の実行パスを確定する
入力     : なし
出力     : なし
"""

import os

import pytesseract


def _configure_tesseract_command():
    """pytesseract が利用するコマンドの場所を探索して設定する。"""
    candidate_paths = [
        os.getenv("TESSERACT_CMD"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidate_paths:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
