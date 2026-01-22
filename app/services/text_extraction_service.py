# text_extraction_service.py
# PyMuPDF 文字提取服務

import os

from app.utils.pdf_utils import (
    extract_page_text,
    convert_pdf_page_to_png,
    convert_image_to_png,
    is_supported_file
)


def extract_text_from_page(file_path: str, page_no: int = 0) -> tuple[str, str]:
    """
    使用 PyMuPDF 從單一頁面提取文字，並轉換為 PNG 圖片（用於 Vision API）

    Args:
        file_path: 檔案路徑
        page_no: 頁碼（0-indexed）

    Returns:
        (提取的文字, PNG 圖片路徑)
        - 提取的文字為 PyMuPDF 直接讀取的文字內容
        - PNG 圖片路徑為臨時檔案，需要在使用後清理

    Raises:
        Exception: 如果文字提取失敗
    """
    try:
        # 1. 判斷檔案類型並轉換為 PNG
        is_supported, file_type = is_supported_file(file_path)

        if file_type == "pdf":
            # PDF 轉 PNG
            png_path = convert_pdf_page_to_png(file_path, page_no)
            
            # 使用 PyMuPDF 提取文字
            extracted_text = extract_page_text(file_path, page_no)
            
        elif file_type == "image":
            # 圖片轉 PNG（如果已經是 PNG 則直接返回）
            png_path = convert_image_to_png(file_path)
            
            # 圖片檔案無法直接提取文字，返回空字串
            extracted_text = ""
            print("⚠️  圖片檔案無法使用 PyMuPDF 提取文字，將僅使用圖片進行辨識")
            
        else:
            raise ValueError(f"不支援的檔案類型：{file_path}")

        print(f"✅ PyMuPDF 文字提取完成，提取出 {len(extracted_text)} 個字元")

    except Exception as e:
        print(f"❌ 文字提取失敗：{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

    # 印出提取的文字內容
    print("\n" + "="*80)
    print("📄 PyMuPDF 提取的文字內容（傳給 LLM）:")
    print("="*80)
    print(extracted_text)
    print("="*80)
    print(f"📊 總字元數：{len(extracted_text)}")
    print("="*80 + "\n")

    # 返回提取的文字和 PNG 路徑
    return extracted_text, png_path


def extract_text_from_all_pages(file_path: str, total_pages: int) -> list[tuple[str, str]]:
    """
    對所有頁面執行文字提取

    Args:
        file_path: 檔案路徑
        total_pages: 總頁數

    Returns:
        提取結果列表，每頁一個 tuple (extracted_text, png_path)

    Raises:
        Exception: 如果文字提取失敗
    """
    results = []
    for page_no in range(total_pages):
        extracted_text, png_path = extract_text_from_page(file_path, page_no)
        results.append((extracted_text, png_path))
    return results
