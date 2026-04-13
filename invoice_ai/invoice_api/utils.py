import cv2
import pytesseract
from pdf2image import convert_from_path
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_ocr_data(file_path):

    # 🔥 STEP 1: Handle PDF
    if file_path.lower().endswith(".pdf"):
        images = convert_from_path(
            file_path,
            poppler_path=r"C:\poppler-25.12.0\Library\bin"
        )

        # take first page
        img = images[0]

        # convert PIL → OpenCV
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    else:
        # normal image
        img = cv2.imread(file_path)

    # 🔍 OCR
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words = []
    boxes = []

    for i in range(len(data['text'])):
        if data['text'][i].strip() != "":
            words.append(data['text'][i])

            x = data['left'][i]
            y = data['top'][i]
            w = data['width'][i]
            h = data['height'][i]

            boxes.append([x, y, x + w, y + h])

    return words, boxes