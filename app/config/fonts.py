"""
ファイル名: fonts.py
目的     : matplotlib のフォント設定を初期化する
概要     : 利用可能な日本語フォントを優先的に検出し、matplotlib の rcParams に設定する
入力     : なし
出力     : なし
"""

from matplotlib import font_manager, pyplot as plt


def _configure_matplotlib_font():
    """日本語フォントがあれば優先的に使用し、なければデフォルトを使う。"""
    preferred_fonts = [
        "Yu Gothic",
        "YuGothic",
        "Meiryo",
        "MS Gothic",
        "Hiragino Sans",
        "Noto Sans CJK JP",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font in preferred_fonts:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"
