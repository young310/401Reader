# mapping_service.py
# 處理英文欄位 ↔ 中文 JSON 的雙向映射

from typing import Dict, Any, List


def map_401_record_to_chinese_json(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    將英文 Record401 反向映射成中文 JSON 格式
    用於儲存編輯後的資料回 DB

    Args:
        record: 英文欄位格式的 401 記錄

    Returns:
        中文 JSON 格式
    """
    return {
        "所屬年月份": f"{record.get('year', '')}年{record.get('month', '')}",
        "申報日期": "",  # 原始資料中有，編輯時不修改
        "INDEX": record.get('month', ''),
        "銷項": {
            "一般稅額銷售額": {
                "應稅": {
                    "三聯式": record.get('triplicateSales', 0),
                    "二聯式": record.get('duplicateSales', 0)
                },
                "零稅率": {
                    "經海關": record.get('customsSales', 0),
                    "非經海關": record.get('nonCustomsSales', 0)
                },
                "免稅": record.get('taxFreeSales', 0)
            },
            "特種稅額銷售額": record.get('specialTaxSales', 0),
            "其他": record.get('otherSales', 0),
            "銷售額合計": record.get('totalSales', 0),
            "銷項退回及折讓": record.get('returnAndAllowance', 0),
            "淨額": record.get('netAmount', 0)
        },
        "進項": {
            "得扣抵": {
                "進貨及費用": record.get('purchaseAndExpense', 0),
                "固定資產": record.get('fixedAssets', 0)
            },
            "減退回及折讓": {
                "進貨及費用": record.get('purchaseReturn', 0),
                "固定資產": record.get('purchaseReturnAssets', 0)
            },
            "合計": {
                "進貨及費用": record.get('totalPurchase', 0),
                "固定資產": record.get('fixedAssets', 0)  # 注意：合計的固定資產通常與得扣抵相同
            },
            "進口貨物金額": record.get('importAmount', 0)
        }
    }


def map_withholding_record_to_chinese_json(record: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    """
    將英文 WithholdingRecord 反向映射成中文 JSON 格式
    用於儲存編輯後的資料回 DB

    Args:
        record: 英文欄位格式的彙總表/憑單記錄
        record_type: 'payment' 或 'income'

    Returns:
        中文 JSON 格式
    """
    # 基礎映射（彙總表和憑單共用欄位）
    chinese_json = {
        "申報期間": record.get('period', ''),
        "申報日期": record.get('filing_date', ''),
        "INDEX": record.get('index', ''),
        "項目": record.get('item', ''),
        "底稿索引": record.get('draft_index', ''),
        "所得類別/代號": record.get('income_type', ''),
        "各類給付總額": record.get('total_payment', 0),
        "扣繳稅額": record.get('withholding_tax', 0)
    }

    # 根據類型添加額外欄位
    if record_type == 'payment':
        chinese_json["扣繳單位名稱"] = record.get('payer_name', '')
    else:  # income
        chinese_json["所得人姓名"] = record.get('payee_name', '')

    return chinese_json


def merge_edited_records_to_result_json(
    original_json: Any,
    edited_records: List[Dict[str, Any]],
    document_type: str,
    detected_stream: Optional[str] = None
) -> Any:
    """
    將前端編輯後的 records 合併回原始的 result_json 格式

    Args:
        original_json: 原始的 result_json（可能是物件或陣列）
        edited_records: 前端編輯後的記錄列表
        document_type: 文件類型 ('401', '403', 'withholding-slip', 'withholding-statement', 'dividend-slip')
        detected_stream: 收支方向 ('支出', '收入', None)

    Returns:
        更新後的 result_json
    """
    # 401/403：單個物件
    if document_type in ['401', '403']:
        if len(edited_records) > 0:
            # 保留原始的申報日期
            original_filing_date = original_json.get('申報日期', '') if isinstance(original_json, dict) else ''
            chinese_json = map_401_record_to_chinese_json(edited_records[0])
            if original_filing_date:
                chinese_json['申報日期'] = original_filing_date
            return chinese_json
        return original_json

    # 彙總表/憑單/股利憑單：陣列
    elif document_type in ['withholding-slip', 'withholding-statement', 'dividend-slip']:
        record_type = 'payment' if detected_stream == '支出' else 'income'
        return [
            map_withholding_record_to_chinese_json(record, record_type)
            for record in edited_records
        ]

    # 未知類型：返回原始資料
    return original_json
