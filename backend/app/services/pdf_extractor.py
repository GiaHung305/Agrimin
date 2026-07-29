from io import BytesIO
from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Trích xuất text thuần từ PDF. KHÔNG làm OCR — chỉ đọc được PDF có text layer sẵn
    (PDF xuất từ Word/Google Docs...), không đọc được PDF scan ảnh thuần.
    Đủ dùng cho quy mô hiện tại; nếu sau này cần đọc PDF scan, mới cân nhắc thêm OCR.
    """
    reader = PdfReader(BytesIO(file_bytes))
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)