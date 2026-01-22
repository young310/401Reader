# pdf_utils.py
# PDF 處理工具（從 withholding_statement_OCR.py 搬移）

import fitz  # PyMuPDF
from typing import Tuple


SUPPORTED_PDF = {".pdf"}
SUPPORTED_IMG = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif"}


def get_pdf_page_count(pdf_path: str) -> int:
    """
    取得 PDF 總頁數

    Args:
        pdf_path: PDF 檔案路徑

    Returns:
        總頁數

    Raises:
        ValueError: 如果 PDF 無效
        FileNotFoundError: 如果檔案不存在
    """
    import os
    
    # 🔧 檢查檔案是否存在（提供更清楚的錯誤訊息）
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"無法開啟 PDF：no such file: '{pdf_path}'")
    
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()
        return page_count
    except FileNotFoundError:
        raise  # 重新拋出 FileNotFoundError
    except Exception as e:
        raise ValueError(f"無法開啟 PDF：{e}")


def pdf_page_to_bytes(pdf_path: str, page_no: int) -> bytes:
    """
    將 PDF 特定頁面轉換為圖片 bytes（PNG 格式）

    Args:
        pdf_path: PDF 檔案路徑
        page_no: 頁碼（0-indexed）

    Returns:
        PNG 圖片的 bytes

    Raises:
        ValueError: 如果頁碼超出範圍或 PDF 無效
    """
    try:
        doc = fitz.open(pdf_path)

        if len(doc) == 0:
            raise ValueError("PDF 無頁面")

        if page_no >= len(doc):
            raise ValueError(f"頁碼 {page_no} 超出範圍（總共 {len(doc)} 頁）")

        # 載入指定頁面
        page = doc.load_page(page_no)

        # 轉換為 PNG 圖片（放大 3 倍以提升 OCR 品質）
        # 使用高品質設定：alpha=False（移除透明度）
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)

        # 轉換為 bytes
        data = pix.tobytes("png")

        doc.close()
        print(f"   OCR 圖片尺寸：{pix.width} x {pix.height} 像素（3x 放大）")
        return data

    except Exception as e:
        raise ValueError(f"PDF 頁面轉換失敗：{e}")


def extract_first_page_text(file_path: str) -> str:
    """
    使用 PyMuPDF 提取 PDF 第一頁的純文字（不呼叫外部 OCR）

    Args:
        file_path: PDF 檔案路徑

    Returns:
        第一頁的純文字內容

    Raises:
        ValueError: 如果無法讀取 PDF
    """
    try:
        doc = fitz.open(file_path)

        if len(doc) == 0:
            raise ValueError("PDF 無頁面")

        # 讀取第一頁
        page = doc.load_page(0)

        # 提取文字
        text = page.get_text()

        doc.close()

        return text.strip()

    except Exception as e:
        raise ValueError(f"提取 PDF 文字失敗：{e}")


def extract_page_text(file_path: str, page_no: int = 0) -> str:
    """
    使用 PyMuPDF 提取 PDF 指定頁面的純文字（不呼叫外部 OCR）

    Args:
        file_path: PDF 檔案路徑
        page_no: 頁碼（0-indexed）

    Returns:
        指定頁面的純文字內容

    Raises:
        ValueError: 如果無法讀取 PDF 或頁碼超出範圍
    """
    try:
        doc = fitz.open(file_path)

        if len(doc) == 0:
            raise ValueError("PDF 無頁面")

        if page_no >= len(doc):
            raise ValueError(f"頁碼 {page_no} 超出範圍（總共 {len(doc)} 頁）")

        # 讀取指定頁面
        page = doc.load_page(page_no)

        # 提取文字
        text = page.get_text()

        doc.close()

        return text.strip()

    except Exception as e:
        raise ValueError(f"提取 PDF 第 {page_no + 1} 頁文字失敗：{e}")


def is_supported_file(file_path: str) -> Tuple[bool, str]:
    """
    檢查檔案是否為支援的格式

    Args:
        file_path: 檔案路徑

    Returns:
        (是否支援, 檔案類型)
        例如: (True, "pdf") 或 (True, "image") 或 (False, "unknown")
    
    Raises:
        FileNotFoundError: 如果檔案不存在
    """
    import os

    # 🔧 檢查檔案是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"檔案不存在：{file_path}")
    
    # 🔧 檢查檔案是否可讀取
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"檔案無法讀取：{file_path}")

    _, ext = os.path.splitext(file_path.lower())

    if ext in SUPPORTED_PDF:
        return True, "pdf"
    elif ext in SUPPORTED_IMG:
        return True, "image"
    else:
        return False, "unknown"


def get_file_bytes(file_path: str, page_no: int = 0) -> bytes:
    """
    取得檔案的 bytes（PDF 會轉換為圖片，圖片直接讀取）

    Args:
        file_path: 檔案路徑
        page_no: 頁碼（僅 PDF 有效，0-indexed）

    Returns:
        檔案的 bytes

    Raises:
        ValueError: 如果檔案格式不支援或讀取失敗
    """
    is_supported, file_type = is_supported_file(file_path)

    if not is_supported:
        raise ValueError(f"不支援的檔案格式：{file_path}")

    if file_type == "pdf":
        return pdf_page_to_bytes(file_path, page_no)
    elif file_type == "image":
        with open(file_path, "rb") as f:
            return f.read()
    else:
        raise ValueError(f"未知的檔案類型：{file_type}")


def convert_pdf_page_to_png(pdf_path: str, page_no: int) -> str:
    """
    將 PDF 特定頁面轉換為 PNG 臨時檔案（用於 Vision API）
    自動壓縮以符合 LLM API 大小限制

    Args:
        pdf_path: PDF 檔案路徑
        page_no: 頁碼（0-indexed）

    Returns:
        PNG 臨時檔案路徑（壓縮後）

    Raises:
        ValueError: 如果頁碼超出範圍或 PDF 無效
        FileNotFoundError: 如果 PDF 檔案不存在
    """
    import tempfile
    import base64

    try:
        doc = fitz.open(pdf_path)

        if len(doc) == 0:
            raise ValueError("PDF 無頁面")

        if page_no >= len(doc):
            raise ValueError(f"頁碼 {page_no} 超出範圍（總共 {len(doc)} 頁）")

        # 載入指定頁面
        page = doc.load_page(page_no)

        # 轉換為 PNG 圖片（放大 3 倍以提升 LLM Vision 品質）
        # 使用高品質設定：alpha=False（移除透明度），dpi=300
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)

        # 建立臨時檔案
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            # 保存為高品質 PNG
            pix.save(tmp_path)

        doc.close()

        # 檢查 base64 大小
        with open(tmp_path, 'rb') as f:
            original_bytes = f.read()
            original_base64_size = len(base64.b64encode(original_bytes))

        print(f"✅ PDF 第 {page_no + 1} 頁已轉換為 PNG：{tmp_path}")
        print(f"   圖片尺寸：{pix.width} x {pix.height} 像素（3x 放大）")
        print(f"   Base64 大小：{original_base64_size:,} bytes ({original_base64_size/1024/1024:.2f} MB)")

        # 如果大小超過限制，進行壓縮
        if original_base64_size > 4.9 * 1024 * 1024:
            print("⚠️  圖片過大，開始壓縮...")
            compressed_path = compress_image_for_llm(tmp_path)
            
            # 刪除原始臨時檔案
            import os
            os.remove(tmp_path)
            
            return compressed_path
        else:
            print("✅ 圖片大小符合要求")
            return tmp_path

    except Exception as e:
        raise ValueError(f"PDF 轉 PNG 失敗：{e}")


def compress_image_for_llm(image_path: str, max_size_mb: float = 4.9) -> str:
    """
    快速壓縮圖片以符合 LLM API 的大小限制（base64 編碼後不超過指定大小）

    Args:
        image_path: 圖片檔案路徑
        max_size_mb: 最大大小（MB），默認 4.9MB（留 0.1MB 緩衝）

    Returns:
        壓縮後的 PNG 檔案路徑

    Raises:
        ValueError: 如果圖片處理失敗
    """
    import os
    import tempfile
    import base64
    from PIL import Image

    max_size_bytes = int(max_size_mb * 1024 * 1024)
    
    try:
        # 開啟圖片
        img = Image.open(image_path)
        
        # 轉換模式
        if img.mode not in ('RGB', 'RGBA', 'L'):
            img = img.convert('RGB')

        # 建立臨時檔案
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        original_size = img.size
        print(f"🔧 快速壓縮圖片：{image_path}")
        print(f"   原始尺寸：{original_size[0]} x {original_size[1]} 像素")
        
        # 🚀 快速策略：直接計算目標尺寸
        # 估算當前圖片的 base64 大小（粗略估算）
        current_pixels = original_size[0] * original_size[1]
        
        # 目標像素數（假設每像素平均 1.5 bytes 在 base64 中）
        target_pixels = max_size_bytes // 2  # 保守估計
        
        if current_pixels > target_pixels:
            # 計算縮放比例
            scale_ratio = (target_pixels / current_pixels) ** 0.5
            scale_ratio = min(scale_ratio, 0.8)  # 最多縮放到 80%
            scale_ratio = max(scale_ratio, 0.2)  # 最少縮放到 20%
            
            new_width = int(original_size[0] * scale_ratio)
            new_height = int(original_size[1] * scale_ratio)
            
            print(f"   計算縮放比例：{scale_ratio:.2f} → {new_width} x {new_height} 像素")
            
            # 縮放圖片
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 🚀 快速壓縮：只嘗試 3 個品質等級
        quality_levels = [75, 50, 25]  # 中等、低、很低
        
        for quality in quality_levels:
            try:
                # 使用 JPEG 壓縮然後轉 PNG
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=True) as jpeg_tmp:
                    if img.mode == 'RGBA':
                        # RGBA 轉 RGB
                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                        rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        rgb_img.save(jpeg_tmp.name, 'JPEG', quality=quality, optimize=True)
                    else:
                        img.save(jpeg_tmp.name, 'JPEG', quality=quality, optimize=True)
                    
                    # 重新開啟並轉為 PNG
                    compressed_img = Image.open(jpeg_tmp.name)
                    compressed_img.save(tmp_path, 'PNG', optimize=True, compress_level=9)
                
                # 檢查大小
                with open(tmp_path, 'rb') as f:
                    img_bytes = f.read()
                    base64_size = len(base64.b64encode(img_bytes))
                
                print(f"   品質 {quality}%：base64 {base64_size:,} bytes ({base64_size/1024/1024:.2f} MB)")
                
                if base64_size <= max_size_bytes:
                    print(f"✅ 快速壓縮成功！")
                    print(f"   最終尺寸：{img.size[0]} x {img.size[1]} 像素")
                    print(f"   Base64 大小：{base64_size:,} bytes ({base64_size/1024/1024:.2f} MB)")
                    return tmp_path
                    
            except Exception as e:
                print(f"   品質 {quality}% 失敗：{e}")
                continue
        
        # 如果還是太大，使用激進壓縮
        print("⚠️  快速壓縮失敗，使用激進壓縮...")
        
        # 極度縮小 + 灰階
        min_size = 400  # 最小邊長
        if img.size[0] > min_size or img.size[1] > min_size:
            # 保持比例縮放到最小邊長
            ratio = min_size / max(img.size)
            new_width = int(img.size[0] * ratio)
            new_height = int(img.size[1] * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 轉灰階
        if img.mode != 'L':
            img = img.convert('L')
        
        # 最低品質
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=True) as jpeg_tmp:
            img.save(jpeg_tmp.name, 'JPEG', quality=10, optimize=True)
            final_img = Image.open(jpeg_tmp.name)
            final_img.save(tmp_path, 'PNG', optimize=True, compress_level=9)
        
        # 最終檢查
        with open(tmp_path, 'rb') as f:
            img_bytes = f.read()
            base64_size = len(base64.b64encode(img_bytes))
        
        if base64_size <= max_size_bytes:
            print(f"✅ 激進壓縮成功！")
            print(f"   最終尺寸：{img.size[0]} x {img.size[1]} 像素（灰階）")
            print(f"   Base64 大小：{base64_size:,} bytes ({base64_size/1024/1024:.2f} MB)")
            return tmp_path
        else:
            raise ValueError(f"無法將圖片壓縮到 {max_size_mb}MB 以下，當前大小：{base64_size/1024/1024:.2f}MB")

    except Exception as e:
        # 清理臨時檔案
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise ValueError(f"圖片壓縮失敗：{e}")


def convert_image_to_png(image_path: str) -> str:
    """
    將圖片檔案轉換為 PNG 臨時檔案（用於 Vision API）
    自動壓縮以符合 LLM API 大小限制

    Args:
        image_path: 圖片檔案路徑

    Returns:
        PNG 檔案路徑（壓縮後的臨時檔案）

    Raises:
        ValueError: 如果圖片轉換失敗
    """
    import os
    import base64

    # 檢查原始檔案的 base64 大小
    try:
        with open(image_path, 'rb') as f:
            original_bytes = f.read()
            original_base64_size = len(base64.b64encode(original_bytes))
        
        print(f"📊 原始圖片 base64 大小：{original_base64_size:,} bytes ({original_base64_size/1024/1024:.2f} MB)")
        
        # 如果已經小於 4.9MB，且是 PNG 格式，直接返回
        _, ext = os.path.splitext(image_path.lower())
        if ext == '.png' and original_base64_size <= 4.9 * 1024 * 1024:
            print("✅ 圖片大小符合要求，直接使用")
            return image_path
        
        # 需要壓縮
        return compress_image_for_llm(image_path)
        
    except Exception as e:
        raise ValueError(f"圖片處理失敗：{e}")
