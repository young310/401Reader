# ocr_service.py
# Azure Document Intelligence OCR 服務

import os

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.pipeline.transport import RequestsTransport

# 403 Custom Model 使用新版 SDK
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

from app.utils.pdf_utils import (
    get_file_bytes,
    convert_pdf_page_to_png,
    convert_image_to_png,
    is_supported_file
)

# 從環境變數讀取 Azure DI 配置（由大專案環境變數提供）
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT")
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY")
AZURE_DI_MODEL = os.getenv("AZURE_DI_MODEL", "prebuilt-invoice")

# Custom Model 共用配置（401/403）
AZURE_DI_CUSTOM_ENDPOINT = os.getenv("AZURE_DI_CUSTOM_ENDPOINT")
AZURE_DI_CUSTOM_KEY = os.getenv("AZURE_DI_CUSTOM_KEY")
AZURE_DI_401_MODEL = os.getenv("AZURE_DI_401_MODEL", "401")
AZURE_DI_403_MODEL = os.getenv("AZURE_DI_403_MODEL", "403")

# Custom Model 的 Field 配置
CUSTOM_MODEL_FIELDS = {
    '401': ['type_date', 'sales', 'zero_tax', 'purchase'],
    '403': ['sales', 'purchase', 'zero_tax', 'no_tax', 'type_date'],
}


def init_ocr_client() -> DocumentAnalysisClient:
    """
    初始化 Azure Document Intelligence 客戶端（舊版 SDK，用於 prebuilt 模型）

    Returns:
        DocumentAnalysisClient 實例
    """
    return DocumentAnalysisClient(
        endpoint=AZURE_DI_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DI_KEY),
        transport=RequestsTransport(connection_verify=True),
    )


def init_custom_ocr_client() -> DocumentIntelligenceClient:
    """
    初始化 Custom Model 客戶端（新版 SDK，401/403 共用）

    Returns:
        DocumentIntelligenceClient 實例
    """
    return DocumentIntelligenceClient(
        endpoint=AZURE_DI_CUSTOM_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DI_CUSTOM_KEY),
    )


def get_field_value(field) -> str:
    """
    取得欄位實際值的工具函式（用於 Custom Model）

    Args:
        field: Custom Model 回傳的欄位物件

    Returns:
        欄位的文字內容，如果為空則返回空字串
    """
    if field is None:
        return ""
    # 優先使用 content，其次 value_string，最後才用 value
    if hasattr(field, "content") and field.content:
        return field.content
    if hasattr(field, "value_string") and field.value_string:
        return field.value_string
    if hasattr(field, "value") and field.value is not None:
        return str(field.value)
    return ""


def run_custom_ocr(file_path: str, page_no: int = 0, document_type: str = '403') -> tuple[str, str]:
    """
    對 401/403 文件執行 Custom Model OCR 處理（通用函數）

    根據 document_type 選擇對應的 Custom Model 和 Field 配置：
    - 401: 4 個欄位 (type_date, sales, zero_tax, purchase)
    - 403: 5 個欄位 (sales, purchase, zero_tax, no_tax, type_date)

    Args:
        file_path: 檔案路徑
        page_no: 頁碼（0-indexed），目前 Custom Model 只處理第一頁
        document_type: 文件類型 ('401' 或 '403')

    Returns:
        (combined_text, png_path)
        - combined_text: 合併欄位的純文字，格式為 field_name=content
        - png_path: PNG 圖片路徑（用於 LLM Vision）

    Raises:
        Exception: 如果 OCR 處理失敗
    """
    # 根據 document_type 取得對應的 model_id 和 field_names
    if document_type == '401':
        model_id = AZURE_DI_401_MODEL
    else:
        model_id = AZURE_DI_403_MODEL

    field_names = CUSTOM_MODEL_FIELDS.get(document_type, CUSTOM_MODEL_FIELDS['403'])

    try:
        print(f"\n{'='*80}")
        print(f"🔧 {document_type} Custom Model OCR 開始處理")
        print(f"{'='*80}")
        print(f"📄 檔案：{file_path}")
        print(f"📄 頁碼：{page_no}")
        print(f"📄 Model ID：{model_id}")
        print(f"📄 Fields：{field_names}")

        # 1. 判斷檔案類型並轉換為 PNG（用於 LLM Vision）
        is_supported, file_type = is_supported_file(file_path)

        if file_type == "pdf":
            png_path = convert_pdf_page_to_png(file_path, page_no)
        elif file_type == "image":
            png_path = convert_image_to_png(file_path)
        else:
            raise ValueError(f"不支援的檔案類型：{file_path}")

        print(f"✅ PNG 圖片已產生：{png_path}")

        # 2. 讀取檔案 bytes
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # 3. 初始化 Custom Model 客戶端
        client = init_custom_ocr_client()

        # 4. 呼叫 Custom Model
        print(f"🔄 呼叫 {document_type} Custom Model (model_id={model_id})...")
        poller = client.begin_analyze_document(
            model_id=model_id,
            body=AnalyzeDocumentRequest(bytes_source=file_bytes)
        )
        result = poller.result()

        # 5. 檢查是否有結果
        if not result.documents:
            print(f"⚠️ {document_type} Custom Model: 沒有偵測到任何 document")
            return "", png_path

        doc = result.documents[0]
        fields = doc.fields

        # 6. 擷取欄位
        field_values = {}

        for field_name in field_names:
            field = fields.get(field_name)
            value = get_field_value(field)

            if not value:
                print(f"⚠️ {document_type} Custom OCR: {field_name} field 為空")
            else:
                # 印出欄位前 100 個字元（避免太長）
                preview = value[:100] + "..." if len(value) > 100 else value
                print(f"✅ {field_name}: {preview}")

            field_values[field_name] = value

        # 7. 合併成 combined_text
        combined_parts = []
        for field_name in field_names:
            value = field_values[field_name]
            combined_parts.append(f"{field_name}={value}")

        combined_text = "\n\n".join(combined_parts)

        # 8. 印出合併後的文字（供 debug）
        print(f"\n{'='*80}")
        print(f"📄 {document_type} Custom OCR 合併結果（傳給 LLM）:")
        print(f"{'='*80}")
        print(combined_text if combined_text else "[無文字內容]")
        print(f"{'='*80}")
        print(f"📊 合併文字字元數：{len(combined_text)}")
        print(f"{'='*80}\n")

        return combined_text, png_path

    except Exception as e:
        print(f"❌ {document_type} Custom OCR 處理失敗：{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def run_ocr_on_page(file_path: str, page_no: int = 0, document_type: str = None) -> tuple[str, str]:
    """
    對單一頁面執行 OCR 處理，並轉換為 PNG 圖片（用於 Vision API）

    根據 document_type 選擇不同的 OCR 模型：
    - '401': 使用 401 Custom Model（專門訓練的模型）
    - '403': 使用 403 Custom Model（專門訓練的模型）
    - 其他: 使用 prebuilt 模型（prebuilt-invoice 或 prebuilt-layout）

    Args:
        file_path: 檔案路徑
        page_no: 頁碼（0-indexed）
        document_type: 文件類型（'401', '403', 'withholding-slip', 'withholding-statement'）

    Returns:
        (OCR 文字結果, PNG 圖片路徑)
        - OCR 文字包含原始文字（不含表格）
        - PNG 圖片路徑為臨時檔案，需要在使用後清理

    Raises:
        Exception: 如果 OCR 處理失敗
    """
    # 根據 document_type 路由到不同的 OCR 處理函數
    if document_type in ['401', '403']:
        print(f"🔀 使用 {document_type} Custom Model OCR")
        return run_custom_ocr(file_path, page_no, document_type)

    # 其他類型使用 prebuilt 模型（現有邏輯）
    print(f"🔀 使用 Prebuilt Model OCR (model={AZURE_DI_MODEL})")
    return run_prebuilt_ocr(file_path, page_no)


def run_prebuilt_ocr(file_path: str, page_no: int = 0) -> tuple[str, str]:
    """
    對單一頁面執行 Prebuilt Model OCR 處理（原有邏輯）

    Args:
        file_path: 檔案路徑
        page_no: 頁碼（0-indexed）

    Returns:
        (OCR 文字結果, PNG 圖片路徑)
        - OCR 文字包含原始文字（不含表格）
        - PNG 圖片路徑為臨時檔案，需要在使用後清理

    Raises:
        Exception: 如果 OCR 處理失敗
    """
    try:
        # 1. 判斷檔案類型並轉換為 PNG
        is_supported, file_type = is_supported_file(file_path)

        if file_type == "pdf":
            # PDF 轉 PNG
            png_path = convert_pdf_page_to_png(file_path, page_no)
        elif file_type == "image":
            # 圖片轉 PNG（如果已經是 PNG 則直接返回）
            png_path = convert_image_to_png(file_path)
        else:
            raise ValueError(f"不支援的檔案類型：{file_path}")

        # 2. 取得檔案的 bytes（用於 OCR）
        content = get_file_bytes(file_path, page_no)

        # 3. 初始化 OCR 客戶端
        ocr_client = init_ocr_client()

        # 4. 執行 OCR
        poller = ocr_client.begin_analyze_document(
            model_id=AZURE_DI_MODEL,
            document=content
        )
        result = poller.result()
        print(f"✅ OCR 完成，辨識出 {len(result.content) if result.content else 0} 個字元")
    except Exception as e:
        print(f"❌ OCR 處理失敗：{type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

    # 5. 🔧 只提取純文字內容（不含表格）
    ocr_text = result.content if result.content else ""

    # 6. 印出表格資訊（僅供 debug，不傳給 LLM）
    if result.tables:
        print(f"📊 偵測到 {len(result.tables)} 個表格（不傳給 LLM）")

    # 7. 印出純文字內容（供 LLM 使用）
    print("\n" + "="*80)
    print("📄 OCR 純文字內容（傳給 LLM）:")
    print("="*80)
    print(ocr_text if ocr_text else "[無文字內容]")
    print("="*80)
    print(f"📊 純文字字元數：{len(ocr_text)}")
    print("="*80 + "\n")

    # 8. 🔧 返回純文字內容（不返回表格）和 PNG 路徑
    return ocr_text, png_path


def run_ocr_on_all_pages(file_path: str, total_pages: int, document_type: str = None) -> list[tuple[str, str]]:
    """
    對所有頁面執行 OCR 處理

    Args:
        file_path: 檔案路徑
        total_pages: 總頁數
        document_type: 文件類型（'401', '403', 'withholding-slip', 'withholding-statement'）

    Returns:
        OCR 結果列表，每頁一個 tuple (ocr_text, png_path)

    Raises:
        Exception: 如果 OCR 處理失敗
    """
    results = []
    for page_no in range(total_pages):
        ocr_text, png_path = run_ocr_on_page(file_path, page_no, document_type)
        results.append((ocr_text, png_path))
    return results
