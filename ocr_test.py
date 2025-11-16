import pytesseract
from PIL import Image
import os

print("Tesseract path:", pytesseract.pytesseract.tesseract_cmd)
print("Current working dir:", os.getcwd())
print("Files in directory:", os.listdir("."))

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    img = Image.open("test.png")
    print("Image loaded OK")
except Exception as e:
    print("Image load error:", e)

# OCR
text = pytesseract.image_to_string(img, lang="jpn")
print("OCR result:", repr(text))
