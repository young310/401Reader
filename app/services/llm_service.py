# llm_service.py
# LLM 服務（支援 Azure OpenAI）

import os
import json
import re
from typing import Optional, Dict, Any

from openai import AzureOpenAI

from app.prompts.prompts import get_prompts_by_group

# 從環境變數讀取 Azure OpenAI 配置
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
MAX_LLM_RETRY = int(os.getenv("MAX_LLM_RETRY", "2"))

# Debug: 檢查 API Key
if AZURE_OPENAI_KEY:
    print(f"🔑 Azure OpenAI API Key 長度: {len(AZURE_OPENAI_KEY)} 字元")
    print(f"🔑 Azure OpenAI Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"🔑 Azure OpenAI Model: {LLM_MODEL}")


def extract_zero_tax_rate_amounts(ocr_text: str) -> tuple[Optional[int], Optional[int]]:
    """
    從 OCR 文字中提取零稅率銷售額（針對 403 表單）

    Args:
        ocr_text: OCR 提取的純文字內容

    Returns:
        (非經海關金額, 經海關金額) - 如果找不到則返回 None
    """
    def clean_number(num_str: str) -> int:
        """清理數字字串，移除逗號並轉換為整數"""
        if not num_str:
            return 0
        return int(num_str.replace(',', '').replace(' ', ''))

    # 移除多餘的空白和換行，但保持基本結構
    cleaned_text = re.sub(r'\s+', ' ', ocr_text.strip())

    print(f"\n🔍 開始 Regex 提取零稅率銷售額...")
    print(f"   OCR 文字長度: {len(ocr_text)} 字元")

    # 先找到零稅率銷售額區塊 - 改進的模式，支援多種格式
    zero_rate_section = None

    # 優先使用直接匹配方法：尋找非經海關和經海關區塊
    if '非經海關' in cleaned_text and '經海關' in cleaned_text:
        non_customs_start = cleaned_text.find('非經海關')
        # 🆕 改進：先尋找代號16（經海關區間的最後一個代號）
        # 零稅率區塊應該在代號16之後不遠處結束
        code_16_match = re.search(r'\b16\b', cleaned_text[non_customs_start:])
        if code_16_match:
            # 🆕 改進：代號16之後，找到第一個小數字（通常是0或其他代號），然後結束
            # 零稅率區塊的結構：...代號16 [可能的小數字] [其他區塊開始]
            search_start = non_customs_start + code_16_match.end()

            # 尋找代號16之後的第一個「大數字」（> 1000），在它之前結束
            # 或者找到代號19、20、23、24等標記
            section_after_16 = cleaned_text[search_start:search_start + 100]

            # 先找第一個大數字的位置
            first_large_num_match = re.search(r'\d{1,3}(?:,\d{3})+|\d{4,}', section_after_16)
            if first_large_num_match:
                # 檢查這個數字是否是大數字（> 1000）
                num_str = first_large_num_match.group(0).replace(',', '')
                if len(num_str) >= 4 or int(num_str) > 1000:
                    # 這是大數字，在它之前結束
                    end_pos = search_start + first_large_num_match.start()
                    print(f"   📍 在代號16後的大數字({first_large_num_match.group(0)})之前結束區塊")
                else:
                    # 這是小數字，繼續尋找下一個標記
                    end_markers = ['稅額.*?計算', '銷售額.*?總.*?計', '代號.*?項.*?目', '本期.*?月.*?銷項稅額', r'\b19\b', r'\b20\b', r'\b23\b', r'\b24\b']
                    end_pos = search_start + 100

                    for marker in end_markers:
                        marker_match = re.search(marker, section_after_16, re.IGNORECASE)
                        if marker_match:
                            marker_pos = search_start + marker_match.start()
                            if marker_pos < end_pos:
                                end_pos = marker_pos
                                break
            else:
                # 沒找到數字，使用標記
                end_markers = ['稅額.*?計算', '銷售額.*?總.*?計', '代號.*?項.*?目', '本期.*?月.*?銷項稅額', r'\b19\b', r'\b20\b', r'\b23\b', r'\b24\b']
                end_pos = search_start + 100

                for marker in end_markers:
                    marker_match = re.search(marker, section_after_16, re.IGNORECASE)
                    if marker_match:
                        marker_pos = search_start + marker_match.start()
                        if marker_pos < end_pos:
                            end_pos = marker_pos
                            break
        else:
            # 找不到代號16，使用原來的邏輯
            end_markers = ['稅額.*?計算', '銷售額.*?總.*?計', '代號.*?項.*?目', '本期.*?月.*?銷項稅額']
            end_pos = len(cleaned_text)
            for marker in end_markers:
                marker_match = re.search(marker, cleaned_text[non_customs_start:], re.IGNORECASE)
                if marker_match:
                    marker_pos = non_customs_start + marker_match.end()
                    if marker_pos < end_pos:
                        end_pos = marker_pos

        zero_rate_section = cleaned_text[non_customs_start:end_pos]
        print(f"   📝 找到零稅率區塊(直接匹配): {zero_rate_section[:200]}...")

    # 備用方案：模式匹配（只有在直接匹配失敗時才使用）
    if not zero_rate_section:
        zero_rate_patterns = [
            r'(零.*?稅率.*?銷.*?售.*?額.*?免稅.*?銷售額.*?)(?=稅額.*?計算|銷售額.*?總.*?計|代號.*?項.*?目|本期.*?月.*?銷項稅額|$)',
            r'(免稅.*?銷售額.*?)(?=稅額.*?計算|銷售額.*?總.*?計|代號.*?項.*?目|本期.*?月.*?銷項稅額|$)',
            r'(非經海關.*?經海關.*?)(?=稅額.*?計算|銷售額.*?總.*?計|代號.*?項.*?目|本期.*?月.*?銷項稅額|$)'
        ]

        for i, pattern in enumerate(zero_rate_patterns):
            zero_rate_match = re.search(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
            if zero_rate_match:
                zero_rate_section = zero_rate_match.group(1)
                print(f"   📝 找到零稅率區塊(模式{i+1}): {zero_rate_section[:200]}...")
                break

    if not zero_rate_section:
        print(f"   ❌ 未找到零稅率區塊")
        return None, None

    non_customs_amount = None
    customs_amount = None

    # 🆕 改進策略：優先尋找所有大數字，然後根據位置和上下文智能分配
    print(f"   🔍 尋找所有大數字...")

    # 先找出所有大數字（金額）及其位置
    all_large_numbers = []
    for match in re.finditer(r'\d{1,3}(?:,\d{3})+|\d{4,}', zero_rate_section):
        num_str = match.group(0)
        cleaned_num = clean_number(num_str)
        if cleaned_num > 30:  # 過濾小數字
            all_large_numbers.append({
                'value': cleaned_num,
                'str': num_str,
                'pos': match.start()
            })

    number_list = [f"{n['str']}@{n['pos']}" for n in all_large_numbers]
    print(f"   📝 找到 {len(all_large_numbers)} 個大數字: {number_list}")

    if len(all_large_numbers) == 0:
        # 沒有找到任何大數字
        print(f"   ✅ 非經海關: 0, 經海關: 0 (未找到任何大數字)")
        return 0, 0

    # 🆕 策略：根據「非經海關」和「經海關」文字位置來分配數字
    non_customs_text_pos = zero_rate_section.find('非經海關')
    customs_text_pos = zero_rate_section.find('經海關')

    print(f"   📍 '非經海關' 位置: {non_customs_text_pos}, '經海關' 位置: {customs_text_pos}")

    # 如果只有一個大數字
    if len(all_large_numbers) == 1:
        num = all_large_numbers[0]
        # 判斷這個數字更靠近哪個文字
        if non_customs_text_pos != -1 and customs_text_pos != -1:
            dist_to_non_customs = abs(num['pos'] - non_customs_text_pos)
            dist_to_customs = abs(num['pos'] - customs_text_pos)
            if dist_to_non_customs < dist_to_customs:
                non_customs_amount = num['value']
                customs_amount = 0
                print(f"   ✅ 只有1個數字，更靠近非經海關: 非經海關={non_customs_amount:,}, 經海關=0")
            else:
                non_customs_amount = 0
                customs_amount = num['value']
                print(f"   ✅ 只有1個數字，更靠近經海關: 非經海關=0, 經海關={customs_amount:,}")
        elif customs_text_pos != -1:
            # 只找到經海關
            customs_amount = num['value']
            non_customs_amount = 0
            print(f"   ✅ 只找到經海關文字: 非經海關=0, 經海關={customs_amount:,}")
        else:
            # 只找到非經海關或都沒找到，默認給非經海關
            non_customs_amount = num['value']
            customs_amount = 0
            print(f"   ✅ 默認分配給非經海關: 非經海關={non_customs_amount:,}, 經海關=0")

    # 如果有兩個或更多大數字
    elif len(all_large_numbers) >= 2:
        # 🆕 策略：智能判斷數字分配
        # 關鍵洞察：
        # 1. 如果有重複數字，可能是 OCR 重複掃描，只取一個作為經海關
        # 2. 根據代號8和代號16的位置來判斷數字歸屬

        # 檢查是否有重複數字
        unique_values = list(set([n['value'] for n in all_large_numbers]))
        print(f"   📝 唯一數字: {[f'{v:,}' for v in unique_values]}")

        # 尋找代號8和代號16的位置
        code_8_pos = -1
        code_16_pos = -1
        for match in re.finditer(r'\b8\b', zero_rate_section):
            code_8_pos = match.start()
            break
        for match in re.finditer(r'\b16\b', zero_rate_section):
            code_16_pos = match.start()
            break

        print(f"   📍 代號8位置: {code_8_pos}, 代號16位置: {code_16_pos}")

        # 策略1：如果只有一個唯一數字（重複的情況），判斷它應該屬於哪個區間
        if len(unique_values) == 1:
            num_value = unique_values[0]
            # 檢查這個數字最早出現在哪個位置
            first_occurrence_pos = all_large_numbers[0]['pos']

            # 🆕 優先判斷：檢查數字是否緊跟在「出口免附證明文件者」或「出口應附證明文件者」之後
            # 這是最強的上下文證據
            non_customs_desc_pattern = r'非經海關.*?出口.*?應附證明文件者'
            customs_desc_pattern = r'經海關.*?出口.*?免附證明文件者'

            # 尋找描述文字的結束位置
            non_customs_desc_end = -1
            customs_desc_end = -1

            non_customs_desc_match = re.search(non_customs_desc_pattern, zero_rate_section[:first_occurrence_pos + 50])
            if non_customs_desc_match:
                non_customs_desc_end = non_customs_desc_match.end()

            customs_desc_match = re.search(customs_desc_pattern, zero_rate_section[:first_occurrence_pos + 50])
            if customs_desc_match:
                customs_desc_end = customs_desc_match.end()

            print(f"   📍 非經海關描述結束位置: {non_customs_desc_end}, 經海關描述結束位置: {customs_desc_end}, 數字位置: {first_occurrence_pos}")

            # 判斷數字更靠近哪個描述
            if customs_desc_end != -1 and abs(first_occurrence_pos - customs_desc_end) < 50:
                # 數字緊跟在經海關描述之後
                non_customs_amount = 0
                customs_amount = num_value
                print(f"   ✅ 唯一數字緊跟在經海關描述後: 非經海關=0, 經海關={customs_amount:,}")
            elif non_customs_desc_end != -1 and abs(first_occurrence_pos - non_customs_desc_end) < 50:
                # 數字緊跟在非經海關描述之後
                non_customs_amount = num_value
                customs_amount = 0
                print(f"   ✅ 唯一數字緊跟在非經海關描述後: 非經海關={non_customs_amount:,}, 經海關=0")
            else:
                # 無法通過描述判斷，使用代號位置判斷
                if code_8_pos != -1 and code_16_pos != -1:
                    if first_occurrence_pos > code_8_pos:
                        # 在代號8之後，可能是經海關區間
                        non_customs_amount = 0
                        customs_amount = num_value
                        print(f"   ✅ 唯一數字在代號8之後: 非經海關=0, 經海關={customs_amount:,}")
                    else:
                        # 在代號8之前，可能是非經海關
                        non_customs_amount = num_value
                        customs_amount = 0
                        print(f"   ✅ 唯一數字在代號8之前: 非經海關={non_customs_amount:,}, 經海關=0")
                else:
                    # 無法判斷，默認為經海關
                    non_customs_amount = 0
                    customs_amount = num_value
                    print(f"   ✅ 唯一數字（無代號信息）: 非經海關=0, 經海關={customs_amount:,}")

        # 策略2：如果有多個唯一數字
        else:
            if customs_text_pos != -1:
                before_customs = [n for n in all_large_numbers if n['pos'] < customs_text_pos]
                after_customs = [n for n in all_large_numbers if n['pos'] >= customs_text_pos]

                print(f"   📝 在'經海關'之前的數字: {[n['str'] for n in before_customs]}")
                print(f"   📝 在'經海關'之後的數字: {[n['str'] for n in after_customs]}")

                # 如果「經海關」之後有>=2個不同的數字
                after_customs_unique = []
                seen_values = set()
                for n in after_customs:
                    if n['value'] not in seen_values:
                        after_customs_unique.append(n)
                        seen_values.add(n['value'])

                if len(after_customs_unique) >= 2:
                    # 取前兩個不同的數字
                    non_customs_amount = after_customs_unique[0]['value']
                    customs_amount = after_customs_unique[1]['value']
                    print(f"   ✅ 經海關後有>=2個不同數字: 非經海關={non_customs_amount:,}, 經海關={customs_amount:,}")
                elif len(after_customs_unique) == 1 and len(before_customs) >= 1:
                    # 一個在前，一個在後
                    non_customs_amount = before_customs[0]['value']
                    customs_amount = after_customs_unique[0]['value']
                    print(f"   ✅ 一個在經海關前，一個在後: 非經海關={non_customs_amount:,}, 經海關={customs_amount:,}")
                elif len(after_customs_unique) == 1:
                    # 只有一個在經海關後
                    customs_amount = after_customs_unique[0]['value']
                    non_customs_amount = 0
                    print(f"   ✅ 只有經海關後有數字: 非經海關=0, 經海關={customs_amount:,}")
                else:
                    # 都在經海關前，取前兩個不同的數字
                    unique_before = []
                    seen_before = set()
                    for n in all_large_numbers:
                        if n['value'] not in seen_before:
                            unique_before.append(n)
                            seen_before.add(n['value'])
                        if len(unique_before) >= 2:
                            break

                    non_customs_amount = unique_before[0]['value']
                    customs_amount = unique_before[1]['value'] if len(unique_before) > 1 else 0
                    print(f"   ✅ 都在經海關前: 非經海關={non_customs_amount:,}, 經海關={customs_amount:,}")
            else:
                # 沒找到「經海關」文字，取前兩個不同的數字
                unique_numbers = []
                seen_values = set()
                for n in all_large_numbers:
                    if n['value'] not in seen_values:
                        unique_numbers.append(n)
                        seen_values.add(n['value'])
                    if len(unique_numbers) >= 2:
                        break

                non_customs_amount = unique_numbers[0]['value']
                customs_amount = unique_numbers[1]['value'] if len(unique_numbers) > 1 else 0
                print(f"   ✅ 未找到經海關文字，按順序分配: 非經海關={non_customs_amount:,}, 經海關={customs_amount:,}")

    # 確保返回值不是None，0是有效值
    if non_customs_amount is None:
        non_customs_amount = 0
    if customs_amount is None:
        customs_amount = 0

    return non_customs_amount, customs_amount


def post_process_401_taxable_amounts(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    對 401 表單的應稅銷售額進行後處理計算
    計算「三聯式」= 三聯式發票 + 收銀機發票銷售額

    Args:
        result: LLM 提取的 JSON 結果

    Returns:
        修正後的 JSON 結果
    """
    print(f"\n🔧 開始 401 應稅銷售額後處理...")

    # 輔助函數：安全轉換為整數
    def safe_int(value):
        """安全地將值轉換為整數，處理字串、逗號等情況"""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # 移除逗號和空格
            value = value.replace(',', '').replace(' ', '').strip()
            if value == '' or value == '-':
                return 0
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0
        return 0

    # 提取原始數值
    三聯式發票 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("三聯式發票", 0))
    收銀機發票 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("收銀機發票銷售額", 0))
    二聯式 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("二聯式", 0))

    print(f"   📊 原始數值 - 三聯式發票: {三聯式發票:,}, 收銀機發票: {收銀機發票:,}, 二聯式: {二聯式:,}")

    # 計算三聯式總額
    三聯式總額 = 三聯式發票 + 收銀機發票

    # 更新結果 - 添加三聯式欄位
    if "銷項" not in result:
        result["銷項"] = {}
    if "一般稅額銷售額" not in result["銷項"]:
        result["銷項"]["一般稅額銷售額"] = {}
    if "應稅" not in result["銷項"]["一般稅額銷售額"]:
        result["銷項"]["一般稅額銷售額"]["應稅"] = {}

    result["銷項"]["一般稅額銷售額"]["應稅"]["三聯式"] = 三聯式總額

    print(f"   ✅ 計算三聯式總額: {三聯式發票:,} + {收銀機發票:,} = {三聯式總額:,}")

    # 提取所有需要的數值（用於卡控驗證）
    零稅率_經海關 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("經海關", 0))
    零稅率_非經海關 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("非經海關", 0))
    海關退回及折讓 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("海關退回及折讓", 0))
    免稅 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("免稅", 0))
    銷項退回及折讓 = safe_int(result.get("銷項", {}).get("銷項退回及折讓", 0))
    特種稅額合計 = safe_int(result.get("銷項", {}).get("特種稅額合計", 0))
    其他 = safe_int(result.get("銷項", {}).get("其他", 0))

    # === 🆕 卡控邏輯（只驗證，不修改 JSON）===
    print(f"\n🔍 開始卡控驗證...")
    warnings = []

    # 卡控 1：應稅合計驗證
    # 公式：三聯式 + 二聯式 - 銷項退回及折讓
    應稅合計_LLM = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("合計", 0))
    應稅合計_計算 = 三聯式總額 + 二聯式 - 銷項退回及折讓

    if 應稅合計_計算 != 應稅合計_LLM:
        warnings.append("應稅")
        print(f"   ⚠️  應稅合計不符：計算值={應稅合計_計算:,}, 表單值={應稅合計_LLM:,}, 差異={abs(應稅合計_計算 - 應稅合計_LLM):,}")
        print(f"      計算公式: {三聯式總額:,} + {二聯式:,} - {銷項退回及折讓:,} = {應稅合計_計算:,}")
    else:
        print(f"   ✅ 應稅合計驗證通過：{應稅合計_計算:,}")

    # 卡控 2：零稅率合計驗證
    # 公式：非經海關 + 經海關 - 海關退回及折讓
    零稅率合計_LLM = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("零稅率銷售額合計", 0))
    零稅率合計_計算 = 零稅率_非經海關 + 零稅率_經海關 - 海關退回及折讓

    if 零稅率合計_計算 != 零稅率合計_LLM:
        warnings.append("零稅率")
        print(f"   ⚠️  零稅率合計不符：計算值={零稅率合計_計算:,}, 表單值={零稅率合計_LLM:,}, 差異={abs(零稅率合計_計算 - 零稅率合計_LLM):,}")
        print(f"      計算公式: {零稅率_非經海關:,} + {零稅率_經海關:,} - {海關退回及折讓:,} = {零稅率合計_計算:,}")
    else:
        print(f"   ✅ 零稅率合計驗證通過：{零稅率合計_計算:,}")

    # 卡控 3：銷售額總計驗證（實際上是淨額）
    # 公式：三聯式 + 二聯式 + 經海關 + 非經海關 + 免稅 + 特種稅額 + 其他 - 銷項退回及折讓 - 海關退回及折讓
    銷售額總計_LLM = safe_int(result.get("銷項", {}).get("銷售額總計", 0))

    銷售額總計_計算 = (三聯式總額 + 二聯式 + 零稅率_經海關 + 零稅率_非經海關 +
                      免稅 + 特種稅額合計 + 其他 -
                      銷項退回及折讓 - 海關退回及折讓)

    if 銷售額總計_計算 != 銷售額總計_LLM:
        warnings.append("總計")
        print(f"   ⚠️  銷售額總計不符：計算值={銷售額總計_計算:,}, 表單值={銷售額總計_LLM:,}, 差異={abs(銷售額總計_計算 - 銷售額總計_LLM):,}")
        print(f"      計算公式: {三聯式總額:,} + {二聯式:,} + {零稅率_經海關:,} + {零稅率_非經海關:,} + {免稅:,} + {特種稅額合計:,} + {其他:,} - {銷項退回及折讓:,} - {海關退回及折讓:,}")
    else:
        print(f"   ✅ 銷售額總計驗證通過：{銷售額總計_計算:,}")

    # 儲存 warnings
    if warnings:
        result["warnings"] = warnings
        result["warnings_acknowledged"] = False
        print(f"\n   ⚠️  發現 {len(warnings)} 個警告：{', '.join(warnings)}")
    else:
        result["warnings"] = []
        result["warnings_acknowledged"] = False
        print(f"\n   ✅ 所有卡控驗證通過")

    return result


def post_process_403_taxable_amounts(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    對 403 表單的應稅銷售額進行後處理計算
    計算「三聯式」= 三聯式發票 + 收銀機發票銷售額

    Args:
        result: LLM 提取的 JSON 結果

    Returns:
        修正後的 JSON 結果
    """
    print(f"\n🔧 開始 403 應稅銷售額後處理...")

    # 輔助函數：安全轉換為整數
    def safe_int(value):
        """安全地將值轉換為整數，處理字串、逗號等情況"""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # 移除逗號和空格
            value = value.replace(',', '').replace(' ', '').strip()
            if value == '' or value == '-':
                return 0
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0
        return 0

    # 提取原始數值
    三聯式發票 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("三聯式發票", 0))
    收銀機發票 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("收銀機發票銷售額", 0))
    二聯式 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("二聯式", 0))

    print(f"   📊 原始數值 - 三聯式發票: {三聯式發票:,}, 收銀機發票: {收銀機發票:,}, 二聯式: {二聯式:,}")

    # 計算三聯式總額
    三聯式總額 = 三聯式發票 + 收銀機發票

    # 更新結果 - 添加三聯式欄位
    if "銷項" not in result:
        result["銷項"] = {}
    if "一般稅額銷售額" not in result["銷項"]:
        result["銷項"]["一般稅額銷售額"] = {}
    if "應稅" not in result["銷項"]["一般稅額銷售額"]:
        result["銷項"]["一般稅額銷售額"]["應稅"] = {}

    result["銷項"]["一般稅額銷售額"]["應稅"]["三聯式"] = 三聯式總額

    print(f"   ✅ 計算三聯式總額: {三聯式發票:,} + {收銀機發票:,} = {三聯式總額:,}")

    # 提取所有需要的數值（用於卡控驗證）
    零稅率_經海關 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("經海關", 0))
    零稅率_非經海關 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("非經海關", 0))
    海關退回及折讓 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("海關退回及折讓", 0))
    免稅 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("免稅", 0))
    銷項退回及折讓 = safe_int(result.get("銷項", {}).get("銷項退回及折讓", 0))
    特種稅額合計 = safe_int(result.get("銷項", {}).get("特種稅額-合計", 0))
    特種稅額退回 = safe_int(result.get("銷項", {}).get("特種稅額-銷售額退回及折讓", 0))
    其他 = safe_int(result.get("銷項", {}).get("其他", 0))

    # === 🆕 卡控邏輯（只驗證，不修改 JSON）===
    print(f"\n🔍 開始卡控驗證...")
    warnings = []

    # 卡控 1：應稅合計驗證
    # 公式：三聯式 + 二聯式 - 銷項退回及折讓
    應稅合計_LLM = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("合計", 0))
    應稅合計_計算 = 三聯式總額 + 二聯式 - 銷項退回及折讓

    if 應稅合計_計算 != 應稅合計_LLM:
        warnings.append("應稅")
        print(f"   ⚠️  應稅合計不符：計算值={應稅合計_計算:,}, 表單值={應稅合計_LLM:,}, 差異={abs(應稅合計_計算 - 應稅合計_LLM):,}")
        print(f"      計算公式: {三聯式總額:,} + {二聯式:,} - {銷項退回及折讓:,} = {應稅合計_計算:,}")
    else:
        print(f"   ✅ 應稅合計驗證通過：{應稅合計_計算:,}")

    # 卡控 2：零稅率合計驗證
    # 公式：非經海關 + 經海關 - 海關退回及折讓
    零稅率合計_LLM = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("零稅率銷售額合計", 0))
    零稅率合計_計算 = 零稅率_非經海關 + 零稅率_經海關 - 海關退回及折讓

    if 零稅率合計_計算 != 零稅率合計_LLM:
        warnings.append("零稅率")
        print(f"   ⚠️  零稅率合計不符：計算值={零稅率合計_計算:,}, 表單值={零稅率合計_LLM:,}, 差異={abs(零稅率合計_計算 - 零稅率合計_LLM):,}")
        print(f"      計算公式: {零稅率_非經海關:,} + {零稅率_經海關:,} - {海關退回及折讓:,} = {零稅率合計_計算:,}")
    else:
        print(f"   ✅ 零稅率合計驗證通過：{零稅率合計_計算:,}")

    # 卡控 3：銷售額總計驗證（實際上是淨額）
    # 公式：三聯式 + 二聯式 + 經海關 + 非經海關 + 免稅 + 特種稅額 + 其他 - 銷項退回及折讓 - 海關退回及折讓 - 特種稅額退回
    銷售額總計_LLM = safe_int(result.get("銷項", {}).get("銷售額總計", 0))
    特種稅額 = 特種稅額合計 + 特種稅額退回  # 403 特種稅額 = 合計 + 退回

    銷售額總計_計算 = (三聯式總額 + 二聯式 + 零稅率_經海關 + 零稅率_非經海關 +
                      免稅 + 特種稅額 + 其他 -
                      銷項退回及折讓 - 海關退回及折讓 - 特種稅額退回)

    if 銷售額總計_計算 != 銷售額總計_LLM:
        warnings.append("總計")
        print(f"   ⚠️  銷售額總計不符：計算值={銷售額總計_計算:,}, 表單值={銷售額總計_LLM:,}, 差異={abs(銷售額總計_計算 - 銷售額總計_LLM):,}")
        print(f"      計算公式: {三聯式總額:,} + {二聯式:,} + {零稅率_經海關:,} + {零稅率_非經海關:,} + {免稅:,} + {特種稅額:,} + {其他:,} - {銷項退回及折讓:,} - {海關退回及折讓:,} - {特種稅額退回:,}")
    else:
        print(f"   ✅ 銷售額總計驗證通過：{銷售額總計_計算:,}")

    # 儲存 warnings
    if warnings:
        result["warnings"] = warnings
        result["warnings_acknowledged"] = False
        print(f"\n   ⚠️  發現 {len(warnings)} 個警告：{', '.join(warnings)}")
    else:
        result["warnings"] = []
        result["warnings_acknowledged"] = False
        print(f"\n   ✅ 所有卡控驗證通過")

    return result


def post_process_403_zero_tax_rate(result: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """
    對 403 表單的零稅率銷售額進行 Regex 後處理

    Args:
        result: LLM 提取的 JSON 結果
        ocr_text: OCR 原始文字

    Returns:
        修正後的 JSON 結果
    """
    print(f"\n🔧 開始 403 零稅率銷售額後處理...")

    # 輔助函數：安全轉換為整數
    def safe_int(value):
        """安全地將值轉換為整數，處理字串、逗號等情況"""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # 移除逗號和空格
            value = value.replace(',', '').replace(' ', '').strip()
            if value == '' or value == '-':
                return 0
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0
        return 0

    # 提取 Regex 結果
    non_customs_regex, customs_regex = extract_zero_tax_rate_amounts(ocr_text)

    # 獲取 LLM 原始結果並轉換為整數
    llm_non_customs = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("非經海關", 0))
    llm_customs = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("零稅率銷售額", {}).get("經海關", 0))

    print(f"   📊 LLM 結果 - 非經海關: {llm_non_customs:,}, 經海關: {llm_customs:,}")
    print(f"   📊 Regex 結果 - 非經海關: {non_customs_regex:,} 經海關: {customs_regex:,}" if non_customs_regex is not None or customs_regex is not None else "   📊 Regex 結果: 未找到")

    # 決定是否需要修正
    corrections_made = []

    # 修正非經海關
    if non_customs_regex is not None and non_customs_regex != llm_non_customs:
        result["銷項"]["一般稅額銷售額"]["零稅率銷售額"]["非經海關"] = non_customs_regex
        corrections_made.append(f"非經海關: {llm_non_customs:,} → {non_customs_regex:,}")

    # 修正經海關
    if customs_regex is not None and customs_regex != llm_customs:
        result["銷項"]["一般稅額銷售額"]["零稅率銷售額"]["經海關"] = customs_regex
        corrections_made.append(f"經海關: {llm_customs:,} → {customs_regex:,}")

    # 重新計算銷售額合計（如果有修正）
    if corrections_made:
        print(f"   ✅ 進行修正: {', '.join(corrections_made)}")

        # 重新計算銷售額合計（使用 safe_int 確保所有值都是整數）
        應稅_三聯式 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("三聯式", 0))
        應稅_二聯式 = safe_int(result.get("銷項", {}).get("一般稅額銷售額", {}).get("應稅", {}).get("二聯式", 0))
        零稅率_非經海關 = safe_int(result["銷項"]["一般稅額銷售額"]["零稅率銷售額"]["非經海關"])
        零稅率_經海關 = safe_int(result["銷項"]["一般稅額銷售額"]["零稅率銷售額"]["經海關"])

        new_total = 應稅_三聯式 + 應稅_二聯式 + 零稅率_非經海關 + 零稅率_經海關
        old_total = safe_int(result.get("銷項", {}).get("銷售額合計", 0))

        result["銷項"]["銷售額合計"] = new_total

        print(f"   🔄 重新計算銷售額合計: {old_total:,} → {new_total:,}")

        # 重新計算淨額
        銷項退回及折讓 = safe_int(result.get("銷項", {}).get("銷項退回及折讓", 0))
        new_net = new_total - 銷項退回及折讓
        old_net = safe_int(result.get("銷項", {}).get("淨額", 0))

        result["銷項"]["淨額"] = new_net

        print(f"   🔄 重新計算淨額: {old_net:,} → {new_net:,}")
    else:
        print(f"   ✅ 無需修正，LLM 結果正確")

    return result


def check_record_warnings(record):
    """
    檢查記錄的各種警告情況
    1. 個人和非個人的給付總額及扣繳稅額是否完全相同
    2. 薪資項目的扣繳稅率是否符合標準 (0%, 5%, 6%, 18%)
    如果發現異常，則標記 has_warning=true

    Args:
        record: 單筆記錄的 dict

    Returns:
        修改後的 record (直接修改原 dict)
    """
    def safe_int(value):
        """安全轉換為整數，處理 None、空字串、非數字等情況"""
        if value is None or value == "":
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def calculate_tax_rate(tax_amount, total_amount):
        """計算扣繳稅率"""
        if total_amount == 0:
            return None  # 無法計算
        return (tax_amount / total_amount) * 100

    def is_valid_tax_rate(rate):
        """檢查稅率是否在標準範圍內 (允許 ±1% 誤差)"""
        if rate is None:
            return True  # 無法計算的情況視為正常

        # 標準稅率範圍 (允許 ±1% 誤差)
        valid_ranges = [
            (0, 1),      # 0% ±1%
            (4, 6),      # 5% ±1%
            (5, 7),      # 6% ±1%
            (17, 19)     # 18% ±1%
        ]

        return any(min_rate <= rate <= max_rate for min_rate, max_rate in valid_ranges)

    # 取得基本數據
    個人給付總額 = safe_int(record.get("個人給付總額"))
    非個人給付總額 = safe_int(record.get("非個人給付總額"))
    個人扣繳稅額 = safe_int(record.get("個人扣繳稅額"))
    非個人扣繳稅額 = safe_int(record.get("非個人扣繳稅額"))
    項目名稱 = record.get("項目", "Unknown")

    warning_reasons = []

    # 檢查1：個人和非個人數據是否完全相同
    if (個人給付總額 == 非個人給付總額 and
        個人扣繳稅額 == 非個人扣繳稅額 and
        not (個人給付總額 == 0 and 個人扣繳稅額 == 0)):
        warning_reasons.append("個人/非個人數據完全相同")

    # 檢查2：薪資項目的扣繳稅率檢查
    if 項目名稱 == "薪資":
        # 檢查個人部分
        個人稅率 = calculate_tax_rate(個人扣繳稅額, 個人給付總額)
        個人稅率異常 = 個人給付總額 > 0 and not is_valid_tax_rate(個人稅率)

        # 檢查非個人部分
        非個人稅率 = calculate_tax_rate(非個人扣繳稅額, 非個人給付總額)
        非個人稅率異常 = 非個人給付總額 > 0 and not is_valid_tax_rate(非個人稅率)

        if 個人稅率異常:
            warning_reasons.append(f"個人扣繳稅率異常 ({個人稅率:.2f}%)")
        if 非個人稅率異常:
            warning_reasons.append(f"非個人扣繳稅率異常 ({非個人稅率:.2f}%)")

    # 如果有任何警告，標記並輸出
    if warning_reasons:
        record["has_warning"] = True
        print(f"   ⚠️  警告：AI辨識信心度不足")

    return record


def calculate_type2_totals(record):
    """
    計算 TYPE2 的各類給付總額和扣繳稅額
    避免 AI 計算錯誤，提高準確性和效能

    Args:
        record: 單筆記錄的 dict

    Returns:
        修改後的 record (直接修改原 dict)
    """
    def safe_int(value):
        """安全轉換為整數，處理 None、空字串、非數字等情況"""
        if value is None or value == "":
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    # 安全取值
    個人給付總額 = safe_int(record.get("個人給付總額"))
    非個人給付總額 = safe_int(record.get("非個人給付總額"))
    個人扣繳稅額 = safe_int(record.get("個人扣繳稅額"))
    非個人扣繳稅額 = safe_int(record.get("非個人扣繳稅額"))

    # 計算總額
    record["各類給付總額"] = 個人給付總額 + 非個人給付總額
    record["扣繳稅額"] = 個人扣繳稅額 + 非個人扣繳稅額

    # Debug 輸出
    項目名稱 = record.get("項目", "Unknown")
    print(f"   💰 計算 {項目名稱}: 各類給付總額={record['各類給付總額']:,} 扣繳稅額={record['扣繳稅額']:,}")

    return record


def init_llm_client() -> AzureOpenAI:
    """
    初始化 Azure OpenAI 客戶端

    Returns:
        AzureOpenAI 實例
    """
    print(f"🔧 LLM Client 初始化:")
    print(f"   Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"   Model: {LLM_MODEL}")
    print(f"   API Version: {AZURE_OPENAI_API_VERSION}")
    print(f"   API Key (前8碼): {AZURE_OPENAI_KEY[:8]}...")

    client = AzureOpenAI(
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

    return client


def run_llm_extraction(
    ocr_text: str,
    group_type: str,
    company_name: str = "",
    retry_count: int = MAX_LLM_RETRY,
    image_path: str = None,
    voucher_count: int = 1
) -> Dict[str, Any]:
    """
    使用 LLM 從 OCR 純文字和圖片中提取結構化資料（Vision API）

    Args:
        ocr_text: OCR 純文字內容（不含表格）
        group_type: 預分類類型（例如 GROUP_A_401）
        company_name: 使用者公司名稱（用於 TYPE2/TYPE3 判斷收支方向）
        retry_count: 最大重試次數
        image_path: PNG 圖片路徑（可選，用於 Vision API）
        voucher_count: 憑證數量（用於股利憑單）

    Returns:
        提取的 JSON 資料（dict）

    Raises:
        RuntimeError: 如果 LLM 提取失敗
    """
    # 取得對應的 Prompt
    system_prompt, user_template = get_prompts_by_group(group_type)

    # 格式化 User Prompt（✅ 包含 OCR 文字）
    user_prompt = user_template.replace("{{COMPANY_NAME}}", company_name)
    user_prompt = user_prompt.replace("{{VOUCHER_COUNT}}", str(voucher_count))  # 🆕 加入憑證數量
    user_prompt = user_prompt.format(ocr_text=ocr_text)

    # 輸出關鍵資訊
    print(f"\n🔍 LLM 提取 [{group_type}] - 使用 Azure OpenAI")
    print(f"   Model: {LLM_MODEL}")
    print(f"   Prompt Type: {group_type}")
    print(f"   Company Name: {company_name}")
    print(f"   ✅ OCR 文字傳入已啟用")
    print(f"   OCR Text Length: {len(ocr_text)} 字元")
    print(f"   Image Path: {image_path if image_path else 'None'}")

    # 準備圖片（如果有）
    image_base64 = None
    if image_path:
        import base64
        try:
            with open(image_path, "rb") as img_file:
                image_bytes = img_file.read()
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # 檢查 base64 大小
            base64_size_mb = len(image_base64) / 1024 / 1024
            print(f"✅ 圖片已編碼為 base64")
            print(f"   檔案大小：{len(image_bytes):,} bytes ({len(image_bytes)/1024/1024:.2f} MB)")
            print(f"   Base64 大小：{len(image_base64):,} 字元 ({base64_size_mb:.2f} MB)")

            # OpenAI API 限制是 20MB
            if base64_size_mb > 19:
                print(f"❌ 圖片 base64 大小超過限制：{base64_size_mb:.2f} MB > 19 MB")
                raise ValueError(f"圖片過大：{base64_size_mb:.2f} MB，超過 API 限制")
            else:
                print(f"✅ 圖片大小符合 API 限制")

        except Exception as e:
            print(f"⚠️  圖片編碼失敗：{e}，將使用純文字模式")
            image_base64 = None

    # ===== 印出完整的傳送內容 =====
    print("\n" + "="*80)
    print("📤 傳送給 LLM 的完整內容")
    print("="*80)
    print("\n【System Prompt】")
    print("-"*80)
    print(system_prompt)
    print("-"*80)

    print("\n【User Prompt（✅ 包含 OCR 文字）】")
    print("-"*80)
    print(user_prompt[:1000] + "..." if len(user_prompt) > 1000 else user_prompt)  # 只顯示前1000字元避免過長
    print("-"*80)

    print(f"\n【OCR 純文字長度】{len(ocr_text)} 字元 (✅ 已傳入)")

    if image_base64:
        print(f"\n【圖片】")
        print(f"✅ 已包含圖片（base64 長度：{len(image_base64)} 字元）")
        print(f"   圖片路徑：{image_path}")
    else:
        print(f"\n【圖片】")
        print(f"❌ 未包含圖片（純文字模式）")

    print("\n" + "="*80)
    print("📋 傳送內容摘要")
    print("="*80)
    print(f"✅ System Prompt: 已包含")
    print(f"✅ User Prompt: 已包含")
    print(f"✅ OCR 純文字: 已傳入（{len(ocr_text)} 字元）")
    print(f"{'✅' if image_base64 else '❌'} 圖片: {'已包含' if image_base64 else '未包含'}")
    print(f"🔧 處理模式: {'OCR 文字 + 圖片' if image_base64 else '純 OCR 文字'}")
    print("="*80 + "\n")
    # ===== END 印出 =====

    # 初始化 LLM 客戶端
    llm_client = init_llm_client()

    last_err: Optional[Exception] = None

    # 重試邏輯
    for i in range(1, retry_count + 1):
        try:
            # 構建訊息內容
            if image_base64:
                # Vision API 模式：包含 OCR 文字和圖片
                user_content = [
                    {
                        "type": "text",
                        "text": user_prompt  # ✅ 包含 OCR 文字
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            else:
                # 純 OCR 文字模式（沒有圖片）
                user_content = user_prompt

            # 呼叫 Azure OpenAI LLM
            resp = llm_client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=9000,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )

            # 提取回應內容 (OpenAI API 格式)
            raw = resp.choices[0].message.content.strip()

            # ===== DEBUG: 顯示 LLM 原始回應 =====
            print("\n" + "="*80)
            print(f"✅ LLM 原始回應 (第 {i} 次嘗試):")
            print("="*80)
            print(raw)
            print("="*80)
            print(f"📊 回應長度：{len(raw)} 字元")
            print("="*80 + "\n")
            # ===== END DEBUG =====

            # 驗證是否為有效 JSON
            try:
                result = json.loads(raw)

                # 🆕 針對 TYPE2 進行後處理計算
                if group_type in ['GROUP_B_SUMMARY_PAYMENT', 'GROUP_B_SUMMARY_INCOME']:
                    print(f"\n🧮 開始計算 TYPE2 總額...")
                    records_processed = 0
                    for record in result.get("records", []):
                        check_record_warnings(record)
                        calculate_type2_totals(record)
                        records_processed += 1
                    print(f"✅ 完成 {records_processed} 筆記錄的計算")

                # 🆕 針對 TYPE1_401 進行應稅銷售額後處理
                if group_type == 'GROUP_A_401':
                    result = post_process_401_taxable_amounts(result)

                # 🆕 針對 TYPE1_403 進行應稅銷售額後處理
                if group_type == 'GROUP_A_403':
                    result = post_process_403_taxable_amounts(result)
                    # 🔧 暫時關閉 Regex 後處理（403 改用 Custom Model，OCR 格式不同）
                    # result = post_process_403_zero_tax_rate(result, ocr_text)

            except json.JSONDecodeError as json_err:
                print(f"❌ JSON 解析失敗：{json_err}")
                print(f"❌ 錯誤位置：第 {json_err.lineno} 行，第 {json_err.colno} 列")
                print(f"❌ 錯誤訊息：{json_err.msg}")

                # 顯示錯誤附近的內容
                lines = raw.split('\n')
                if 0 < json_err.lineno <= len(lines):
                    error_line = lines[json_err.lineno - 1]
                    print(f"❌ 錯誤行內容：{error_line}")
                    if json_err.colno > 0:
                        print(f"❌ 錯誤位置：{' ' * (json_err.colno - 1)}^")

                # 嘗試清理常見的 JSON 格式問題
                print("\n🔧 嘗試修復 JSON 格式...")

                # 移除可能的 Markdown 代碼塊標記
                cleaned = raw.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]
                if cleaned.startswith('```'):
                    cleaned = cleaned[3:]
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                # 修復常見的數學表達式問題（例如：93116159 + 4922）
                # 先保護「所屬年月份」欄位，避免被誤判為數學表達式
                # 例如：「113年11-12月」不應該被計算
                date_pattern = r'("所屬年月份"\s*:\s*"[^"]*")'
                date_matches = re.findall(date_pattern, cleaned)
                date_placeholders = {}
                for idx, match in enumerate(date_matches):
                    placeholder = f"__DATE_PLACEHOLDER_{idx}__"
                    date_placeholders[placeholder] = match
                    cleaned = cleaned.replace(match, placeholder)

                # 找出所有的數學表達式並計算結果
                def safe_eval_math_expr(match):
                    expr = match.group(0)
                    try:
                        # 只允許基本的數學運算（加減乘除）
                        # 使用 ast.literal_eval 的安全替代方案
                        import ast
                        # 驗證只包含數字和基本運算符
                        if re.match(r'^[\d\s\+\-\*\/\(\)]+$', expr):
                            # 安全地計算簡單數學表達式
                            expr_clean = expr.replace(' ', '')
                            # 手動解析加減運算
                            result = 0
                            current_num = ''
                            current_op = '+'
                            for char in expr_clean + '+':
                                if char.isdigit():
                                    current_num += char
                                elif char in '+-':
                                    if current_num:
                                        if current_op == '+':
                                            result += int(current_num)
                                        else:
                                            result -= int(current_num)
                                        current_num = ''
                                    current_op = char
                            print(f"   🔢 計算表達式：{expr} = {result}")
                            return str(result)
                        return expr
                    except:
                        return expr

                # 匹配數字運算表達式（例如：123 + 456 或 123+456）
                cleaned = re.sub(r'\d+\s*[\+\-]\s*\d+(?:\s*[\+\-]\s*\d+)*', safe_eval_math_expr, cleaned)

                # 恢復「所屬年月份」欄位
                for placeholder, original in date_placeholders.items():
                    cleaned = cleaned.replace(placeholder, original)

                # 嘗試再次解析
                try:
                    result = json.loads(cleaned)
                    print("✅ JSON 修復成功！")

                    # 🆕 針對 TYPE2 進行後處理計算（修復後）
                    if group_type in ['GROUP_B_SUMMARY_PAYMENT', 'GROUP_B_SUMMARY_INCOME']:
                        print(f"\n🧮 開始計算 TYPE2 總額（修復後）...")
                        records_processed = 0
                        for record in result.get("records", []):
                            check_record_warnings(record)
                            calculate_type2_totals(record)
                            records_processed += 1
                        print(f"✅ 完成 {records_processed} 筆記錄的計算")

                    # 🆕 針對 TYPE1_401 進行應稅銷售額後處理（修復後）
                    if group_type == 'GROUP_A_401':
                        result = post_process_401_taxable_amounts(result)

                    # 🆕 針對 TYPE1_403 進行應稅銷售額後處理（修復後）
                    if group_type == 'GROUP_A_403':
                        result = post_process_403_taxable_amounts(result)
                        # 🔧 暫時關閉 Regex 後處理（403 改用 Custom Model，OCR 格式不同）
                        # result = post_process_403_zero_tax_rate(result, ocr_text)

                except json.JSONDecodeError as second_err:
                    # 如果還是失敗，拋出更詳細的錯誤訊息
                    error_context = f"LLM提取失敗：{json_err.msg} (第 {json_err.lineno} 行，第 {json_err.colno} 列)"
                    print(f"❌ 修復失敗：{error_context}")
                    print(f"❌ 第二次錯誤：{second_err}")
                    raise RuntimeError(error_context) from json_err

            # ===== DEBUG: 顯示解析後的 JSON =====
            print("\n" + "="*80)
            print("✅ 解析後的 JSON (Python dict):")
            print("="*80)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("="*80)

            # 顯示關鍵欄位
            if "stream" in result:
                print(f"\n🔍 收支方向 (stream)：{result['stream']}")
            if "扣繳單位名稱" in result:
                print(f"🔍 扣繳單位名稱：{result['扣繳單位名稱']}")
            if "records" in result:
                print(f"🔍 紀錄數量：{len(result['records'])} 筆")
                for idx, record in enumerate(result['records'], 1):
                    print(f"   第 {idx} 筆：{record.get('項目', 'N/A')} - 給付總額：{record.get('各類給付總額', 0)}")

            print("="*80 + "\n")
            # ===== END DEBUG =====

            return result

        except Exception as e:
            last_err = e
            print(f"⚠️  LLM 第 {i} 次嘗試失敗：{e}")

    # 所有重試都失敗
    raise RuntimeError(f"LLM 提取失敗：{last_err}")


def extract_company_name_from_result(
    result_json,
    document_type: str
) -> Optional[str]:
    """
    從 LLM 結果中提取公司/個人名稱

    Args:
        result_json: LLM 提取的 JSON 結果（dict格式）
        document_type: 文件類型 ('401', '403', 'withholding-slip', 'withholding-statement', 'dividend-slip')

    Returns:
        公司/個人名稱（如果有的話）
    """
    # TYPE1 (401/403) 沒有公司名稱欄位
    if document_type in ['401', '403']:
        return None

    # TYPE2、TYPE3、TYPE4 統一處理
    if isinstance(result_json, dict):
        # 檢查是否為多頁格式
        if "頁面資料" in result_json:
            # 多頁檔案：取第一頁的扣繳單位名稱
            pages = result_json.get("頁面資料", [])
            if pages and len(pages) > 0:
                first_page = pages[0]
                if isinstance(first_page, dict):
                    return first_page.get("扣繳單位名稱")
        else:
            # 單頁檔案：直接從 root 提取「扣繳單位名稱」
            return result_json.get("扣繳單位名稱")

    return None


def detect_stream_from_result(
    result_json: Dict[str, Any],
    document_type: str
) -> Optional[str]:
    """
    從 LLM 結果判斷是「支出」還是「收入」

    注意：此函數已棄用，請使用 tasks.py 中的 determine_detected_stream()

    Args:
        result_json: LLM 提取的 JSON 結果
        document_type: 文件類型 ('401', '403', 'withholding-slip', 'withholding-statement')

    Returns:
        "支出" 或 "收入" 或 None（TYPE1 沒有收支概念）
    """
    # TYPE1 (401/403) 沒有收支概念
    if document_type in ['401', '403']:
        return None

    # 直接從 JSON 結果讀取 stream 欄位
    return result_json.get("stream")
