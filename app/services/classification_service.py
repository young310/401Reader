# classification_service.py
# 快速預分類服務（不呼叫 LLM，基於檔名和首頁 OCR 關鍵字）

from typing import Tuple


def quick_classify(filename: str, first_page_ocr: str) -> str:
    """
    基於檔名和首頁 OCR 文字快速分類文件

    不呼叫 LLM，僅使用規則匹配，速度快但可能不準確。
    最終的精確分類由 LLM 執行。

    Args:
        filename: 原始檔名
        first_page_ocr: 首頁 OCR 文字（前 2000 字元即可）

    Returns:
        預分類類型:
        - GROUP_A_401: 401 申報書
        - GROUP_A_403: 403 申報書
        - GROUP_B_SUMMARY_PAYMENT: 各類所得扣繳暨免扣繳憑單申報書（彙總表）- 支出
        - GROUP_B_SUMMARY_INCOME: 各類所得扣繳暨免扣繳憑單申報書（彙總表）- 收入
        - GROUP_B_CERTIFICATE_PAYMENT: 各類所得扣繳暨免扣繳憑單 - 支出
        - GROUP_B_CERTIFICATE_INCOME: 各類所得扣繳暨免扣繳憑單 - 收入
        - GROUP_B_DIVIDEND_PAYMENT: 股利憑單 - 支出
        - GROUP_B_DIVIDEND_INCOME: 股利憑單 - 收入
        - UNKNOWN: 無法辨識
    """
    filename_lower = filename.lower()
    ocr_lower = first_page_ocr[:2000].lower()  # 只取前 2000 字元加快處理

    # =============================
    # 規則 1: 檢查 401/403
    # =============================
    if "401" in filename_lower or "401" in ocr_lower:
        return "GROUP_A_401"

    if "403" in filename_lower or "403" in ocr_lower:
        return "GROUP_A_403"

    # =============================
    # 規則 2: 檢查股利憑單
    # =============================
    dividend_keywords = ["股利", "股息", "盈餘分配", "現金股利", "股票股利", "資本公積"]
    is_dividend = any(k in ocr_lower for k in dividend_keywords)
    
    if is_dividend:
        # 檢查收入/支出關鍵字
        income_keywords = ["收益", "收入", "所得人姓名", "受領人姓名"]
        has_income = any(k in ocr_lower for k in income_keywords)
        
        payment_keywords = ["給付", "支出", "扣繳單位名稱", "扣繳義務人", "營利事業名稱"]
        has_payment = any(k in ocr_lower for k in payment_keywords)
        
        if has_payment and not has_income:
            return "GROUP_B_DIVIDEND_PAYMENT"
        elif has_income and not has_payment:
            return "GROUP_B_DIVIDEND_INCOME"
        elif has_payment:  # 如果兩者都有，優先判斷為支出
            return "GROUP_B_DIVIDEND_PAYMENT"
        else:
            # 無法判斷收支，默認為支出
            return "GROUP_B_DIVIDEND_PAYMENT"

    # =============================
    # 規則 3: 檢查是否為彙總表或憑單
    # =============================
    is_summary = "彙總表" in ocr_lower or "汇总表" in ocr_lower
    is_certificate = ("憑單" in ocr_lower or "凭单" in ocr_lower) and not is_summary

    # 如果無法判斷是彙總表還是憑單，使用額外關鍵字輔助
    if not is_summary and not is_certificate:
        # 彙總表通常有「各類所得扣繳單位稅籍編號」或「申報書」
        if "各類所得扣繳單位稅籍編號" in ocr_lower or "申報書" in ocr_lower:
            is_summary = True
        # 憑單通常有「受領人」、「身分證統一編號」、「所得人姓名」
        elif any(k in ocr_lower for k in ["受領人", "所得人姓名", "身分證統一編號"]):
            is_certificate = True

    # =============================
    # 規則 4: 檢查收入/支出關鍵字
    # =============================
    # 收入關鍵字
    income_keywords = ["收益", "收入", "所得人姓名", "受領人姓名"]
    has_income = any(k in ocr_lower for k in income_keywords)

    # 支出關鍵字
    payment_keywords = ["給付", "支出", "扣繳單位名稱", "扣繳義務人"]
    has_payment = any(k in ocr_lower for k in payment_keywords)

    # =============================
    # 規則 5: 根據組合判斷類型
    # =============================
    if is_summary:
        # 彙總表
        if has_payment and not has_income:
            return "GROUP_B_SUMMARY_PAYMENT"
        elif has_income and not has_payment:
            return "GROUP_B_SUMMARY_INCOME"
        elif has_payment:  # 如果兩者都有，優先判斷為支出
            return "GROUP_B_SUMMARY_PAYMENT"
        else:
            # 無法判斷收支，默認為支出
            return "GROUP_B_SUMMARY_PAYMENT"

    if is_certificate:
        # 憑單
        if has_payment and not has_income:
            return "GROUP_B_CERTIFICATE_PAYMENT"
        elif has_income and not has_payment:
            return "GROUP_B_CERTIFICATE_INCOME"
        elif has_payment:  # 如果兩者都有，優先判斷為支出
            return "GROUP_B_CERTIFICATE_PAYMENT"
        else:
            # 無法判斷收支，默認為支出
            return "GROUP_B_CERTIFICATE_PAYMENT"

    # =============================
    # 規則 6: 無法辨識
    # =============================
    return "UNKNOWN"


def get_group_display_name(group_type: str) -> str:
    """
    取得群組的顯示名稱（用於前端顯示）

    Args:
        group_type: 預分類類型

    Returns:
        顯示名稱
    """
    display_names = {
        "GROUP_A_401": "營業人銷售額與稅額申報書(401)",
        "GROUP_A_403": "營業人銷售額與稅額申報書(403)",
        "GROUP_B_SUMMARY_PAYMENT": "各類所得扣繳暨免扣繳憑單申報書（彙總表）- 支出",
        "GROUP_B_SUMMARY_INCOME": "各類所得扣繳暨免扣繳憑單申報書（彙總表）- 收入",
        "GROUP_B_CERTIFICATE_PAYMENT": "各類所得扣繳暨免扣繳憑單 - 支出",
        "GROUP_B_CERTIFICATE_INCOME": "各類所得扣繳暨免扣繳憑單 - 收入",
        "GROUP_B_DIVIDEND_PAYMENT": "股利憑單 - 支出",
        "GROUP_B_DIVIDEND_INCOME": "股利憑單 - 收入",
        "UNKNOWN": "無法辨識",
    }
    return display_names.get(group_type, group_type)


def group_files_by_type(files_info: list[dict]) -> dict[str, int]:
    """
    統計各群組的檔案數量

    Args:
        files_info: 檔案資訊列表，每個元素包含 {"document_type": "401", "detected_stream": "支出", ...}

    Returns:
        群組統計字典，例如: {"401": 2, "withholding-slip—支出": 5}
    """
    groups = {}
    for file_info in files_info:
        document_type = file_info.get("document_type", "UNKNOWN")
        detected_stream = file_info.get("detected_stream")
        
        # 組合顯示名稱
        if document_type in ['401', '403']:
            group_key = document_type
        elif detected_stream:
            group_key = f"{document_type}—{detected_stream}"
        else:
            group_key = document_type
            
        groups[group_key] = groups.get(group_key, 0) + 1
    return groups
