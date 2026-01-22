#!/usr/bin/env python3
"""
扣繳單位稅籍編號扣繳暨免扣繳憑單申報書 (KK-1) PDF 解析器 V3
結合 OCR 支持和改進的解析邏輯
"""

import pdfplumber
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class FormKK1ParserV3:
    """KK-1 扣繳申報書解析器 V3 - 支持 OCR"""

    def __init__(self, pdf_path: str, use_ocr: bool = True):
        self.pdf_path = pdf_path
        self.text = ""
        self.lines = []
        self.data = {}
        self.use_ocr = use_ocr and OCR_AVAILABLE

    def extract_text(self):
        """提取 PDF 文本內容"""
        # 首先嘗試直接提取文本
        with pdfplumber.open(self.pdf_path) as pdf:
            self.text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    self.text += page_text + "\n"

        # 如果沒有文本且 OCR 可用，使用 OCR
        if not self.text.strip() and self.use_ocr:
            print("PDF 無文本層，使用 OCR 進行文字識別...")
            self.text = self.extract_text_with_ocr()

        self.lines = self.text.split('\n')
        return self.text

    def extract_text_with_ocr(self) -> str:
        """使用 OCR 提取文本"""
        try:
            images = convert_from_path(self.pdf_path, dpi=400)  # 提高 DPI 以改善識別
            text = ""
            for i, image in enumerate(images):
                print(f"正在 OCR 處理第 {i+1}/{len(images)} 頁...")
                # 使用繁體中文 OCR
                page_text = pytesseract.image_to_string(image, lang='chi_tra+eng')
                text += page_text + "\n"
            return text
        except Exception as e:
            print(f"OCR 提取失敗: {e}")
            print("提示：請安裝 pdf2image 和 pytesseract")
            print("  pip install pdf2image pytesseract")
            print("  並安裝 Tesseract OCR 引擎")
            return ""

    def safe_int(self, value: str) -> int:
        """安全轉換為整數，移除逗號、點和空格"""
        if not value or value.strip() == "" or value.strip() == "-":
            return 0
        try:
            # 移除常見噪音字符
            clean_value = re.sub(r'[,.\s元|｜-]', '', value)
            return int(clean_value) if clean_value else 0
        except ValueError:
            return 0

    def extract_field(self, pattern: str, default: str = "") -> str:
        """提取單個字段"""
        match = re.search(pattern, self.text, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else default

    def parse_basic_info(self) -> Dict[str, Any]:
        """解析基本信息"""
        # 提取統一編號
        receipt_no = self.extract_field(r"統\s*一\s*編\s*號\s*[「\|]?\s*(\d+)")
        if not receipt_no:
            receipt_no = self.extract_field(r"統\s*[\-一]\s*編\s*號\s*[「\|]?\s*(\d+)")

        # 提取扣繳單位稅籍編號
        withholding_tax_no = self.extract_field(r"扣繳單位稅籍編號\s*(\d+)")

        # 提取名稱 - 處理 OCR 可能產生的 | 符號
        name = self.extract_field(r"名\s*稱\s*[\|｜]?\s*(.+?)(?:\n|地址)")
        if name:
            name = name.replace('|', '').replace('｜', '').strip()

        # 提取地址
        address = self.extract_field(r"地\s*址\s*[\|｜]?\s*(.+?)(?:\n|扣繳單位|本單位)")
        if address:
            address = address.replace('|', '').replace('｜', '').strip()

        # 提取扣繳義務人/負責人
        withholding_agent = self.extract_field(r"負責人[、，]\s*代表人或管理人[\(（]簽章[\)）]：?\s*(\S+)")
        if not withholding_agent:
            withholding_agent = self.extract_field(r"扣繳\s*義務人.*?[\(（]簽章[\)）]\s*(\S+)")

        # 提取期間
        period = self.extract_field(r"本單位自\s*(\d+\s*年\s*\d+\s*月\s*\d+\s*日\s*至\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日)\s*止")
        if period:
            period = re.sub(r'\s+', '', period)  # 移除空格

        # 提取房屋稅籍編號
        house_tax_no = self.extract_field(r"房屋稅籍編號.*?([A-Z]\d{10,})")

        return {
            "統一編號": receipt_no,
            "扣繳單位稅籍編號": withholding_tax_no,
            "房屋稅籍編號": house_tax_no,
            "名稱": name,
            "地址": address,
            "扣繳義務人": withholding_agent,
            "申報期間": period
        }

    def parse_income_items(self) -> List[Dict[str, Any]]:
        """解析所有所得項目"""
        items = []
        
        # 關鍵字映射 - 優先使用關鍵字識別
        keyword_map = [
            ("薪資", "50", "薪資"),  # 注意：薪資代號可能是 50
            ("稿費", "9B", "稿費等項"),
            ("執行業務", "9A", "執行業務報酬"),
            ("利息", "5A", "利息"),
            ("刷息", "5A", "利息"), # OCR 修正
            ("刷 息", "5A", "利息"), # OCR 修正
            ("租賃", "51", "租賃"),
            ("權利金", "52", "權利金"), # 修正 KK-4 識別問題
            ("股利", "54", "股利或盈餘"),
            ("競技", "91", "競技、競賽及機會中獎獎金"),
            ("機會中獎", "91", "競技、競賽及機會中獎獎金"),
            ("退職", "93", "退職所得"),
            ("財產交易", "76", "財產交易所得"),
            ("跨境銷售", "98", "外國營利事業跨境銷售電子勞務所得"),
            ("電子勞務", "A2", "外國營利事業跨境銷售電子勞務所得"),
            ("A2", "A2", "外國營利事業跨境銷售電子勞務所得"),
            ("營業利潤", "A3", "外國營利事業取得勞務報酬或營業利潤"),
            ("勞務報酬", "A3", "外國營利事業取得勞務報酬或營業利潤"),
            ("A3", "A3", "外國營利事業取得勞務報酬或營業利潤"),
            ("所得稅法第25條", "A4", "外國營利事業適用所得稅法第25條所得"),
            ("A4", "A4", "外國營利事業適用所得稅法第25條所得"),
            ("A", "A", "前4項以外之其他所得"), # 匹配單獨的 A
            ("其他", "92", "其他"),
        ]

        last_matched_name = "未知"
        last_matched_code = "UNKNOWN"

        # 遍歷所有行，查找包含起迄號碼的行
        for line in self.lines:
            # 1. 檢查這一行是否有新的所得類別關鍵字 (即使沒有數據)
            found_new_type = False
            for key, code, name in keyword_map:
                # 構建關鍵字 regex
                if all(ord(c) < 128 for c in key):
                        key_regex = re.escape(key)
                else:
                        key_regex = r"\s*".join(list(key))
                
                if re.search(key_regex, line):
                    last_matched_name = name
                    last_matched_code = code
                    found_new_type = True
                    break
                
                # 代號匹配
                if code in line and len(code) > 1:
                    if code.isdigit():
                        if re.search(rf'(^|[^\d]){code}([^\d]|$)', line):
                            last_matched_name = name
                            last_matched_code = code
                            found_new_type = True
                            break
                    else:
                        if code in line:
                            last_matched_name = name
                            last_matched_code = code
                            found_new_type = True
                            break
            
            # 2. 嘗試提取數據
            # 策略 A: 有起迄號碼 (標準情況)
            range_match = re.search(r'([0-9A-Z]{8}-[0-9A-Z]{8})', line)
            
            # 策略 B: 無起迄號碼，但有明顯的金額數據 (KK-3 情況)
            # 條件: 已經匹配到類型，且行中有大數字 (e.g. > 1000)，且該行不是 Total 行
            # 加強過濾: 排除頁尾資訊 (電話, 日期, 編號) 以及 合計行
            
            # 使用更寬鬆的合計行判斷：以 "合" 或 "含" 開頭 (忽略前面的 | 和空格)
            is_total_line = re.search(r"^[\|\s]*[合含]", line) or re.search(r"(合計|總\s*計|含\s*計|含\s*加\s*圖)", line)
            
            is_footer_noise = False
            if re.search(r"(電話|日|號)", line):
                is_footer_noise = True
            
            # 排除看起來像 ID 的 (e.g. A123456789)
            if re.search(r"[A-Z]\d{9,}", line):
                 is_footer_noise = True

            amounts_in_line = re.findall(r'[\d,.]+', line)
            # 必須有至少一個合理的金額 (大於 1000)
            large_amounts = [self.safe_int(x) for x in amounts_in_line if self.safe_int(x) > 1000]
            
            is_data_line = False
            range_str = ""
            count = 0
            amount = 0
            tax = 0
            
            if range_match:
                is_data_line = True
                range_str = range_match.group(1)
                
                # 提取數據 logic
                pre_range = line.split(range_str)[0]
                count_match = re.search(r'(\d+)\s*$', pre_range)
                count = self.safe_int(count_match.group(1)) if count_match else 0
                
                post_range = line.split(range_str)[1]
                amounts = re.findall(r'([\d,.]+)', post_range)
                
                # 如果當前行沒有足夠的金額，嘗試往下找
                if len(amounts) < 2:
                    # 獲取當前行索引
                    try:
                        current_idx = self.lines.index(line)
                        # 往下看 5 行
                        lookahead_text = " ".join(self.lines[current_idx+1 : current_idx+6])
                        more_amounts = re.findall(r'([\d,.]+)', lookahead_text)
                        amounts.extend(more_amounts)
                    except ValueError:
                        pass
                
                # 清理並轉換
                valid_amounts = []
                for a in amounts:
                    val = self.safe_int(a)
                    if val > 0:
                        valid_amounts.append(val)
                
                # print(f"DEBUG: Valid amounts for {range_str}: {valid_amounts}")
                
                # 智能分配 Amount, Tax
                valid_amounts.sort(reverse=True)
                
                if len(valid_amounts) >= 1:
                    amount = valid_amounts[0]
                    if len(valid_amounts) >= 2:
                        tax = valid_amounts[1]
                
                # print(f"DEBUG: Range {range_str} found. Amounts: {valid_amounts}")

            elif not range_match and len(large_amounts) >= 2 and last_matched_code != "UNKNOWN" and not is_total_line and not is_footer_noise:
                # 嘗試解析無 range 的數據行 (嚴格模式：必須有金額和稅額)
                # 假設如果有兩個大數字，一個是金額，一個是稅額
                # 排序：大的是金額，小的是稅額
                large_amounts.sort(reverse=True)
                amount = large_amounts[0]
                tax = large_amounts[1]
                
                # 只有當金額看起來合理時才接受
                if amount > 0:
                    count = 1 
                    is_data_line = True
                    range_str = "Unknown"

            if is_data_line and amount > 0:
                # 數據修復啟發式
                # 1. 如果金額等於稅額，且金額 > 0，可能是金額少讀了一個 0 (常見於 10% 稅率)
                if amount == tax and amount > 0:
                     amount = amount * 10
                
                # 構建 item
                # 判斷個人/非個人
                # 如果是 KK-3 (無 range)，假設是非個人 (因為 KK 表單主要是非個人?)
                is_non_person = True 
                
                item = {
                    "所得類別": last_matched_name,
                    "代號": last_matched_code,
                    "個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0},
                    "非個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
                }
                
                target_key = "非個人" if is_non_person else "個人"
                item[target_key] = {
                    "份數": count,
                    "起迄號碼": range_str,
                    "給付總額": amount,
                    "扣繳稅額": tax
                }

                # 檢查是否已存在
                existing = next((x for x in items if x['代號'] == last_matched_code), None)
                if existing:
                    # 如果現有項目的金額為0，直接覆蓋
                    if existing[target_key]['給付總額'] == 0:
                         existing[target_key] = item[target_key]
                    else:
                        # 只有當新項目的金額與現有項目不重複時才累加?
                        # 簡單累加，假設 OCR 讀到了多行
                        existing[target_key]['份數'] += count
                        existing[target_key]['給付總額'] += amount
                        existing[target_key]['扣繳稅額'] += tax
                else:
                    items.append(item)

        return items

    def parse_total(self) -> Dict[str, Any]:
        """解析合計數據"""
        # 尋找包含 3 個以上大數字的行，或者是包含 "合" "計" 的行
        candidate_indices = []
        for i, line in enumerate(self.lines):
            # 使用更寬鬆的判斷：以 "合" 或 "含" 開頭，或者包含 "合計" 等關鍵字
            if re.search(r"^[\|\s]*[合含]", line) or re.search(r"(合計|總\s*計|含\s*計|含\s*加\s*圖)", line):
                 candidate_indices.append(i)
        
        parsed_total = self._empty_total()
        
        for idx in candidate_indices:
             # 提取當前行及後5行的所有數字
             combined_text = " ".join(self.lines[idx:idx+5])
             
             # 忽略表頭 (包含 "代號" 或 "項別")
             if re.search(r"(代號|項別)", combined_text):
                 continue

             # 提取所有數字
             nums_str = re.findall(r'[\d,.]+', combined_text)
             nums = [self.safe_int(x) for x in nums_str]
             nums = [n for n in nums if n > 0] # 過濾 0
             
             if not nums:
                 continue

             # 智能分配 Count, Amount, Tax
             # 假設 Amount 最大
             # Tax 次大 (但必須比 Amount 小)
             # Count 最小
             
             nums.sort(reverse=True)
             
             if len(nums) >= 2:
                 t_amount = nums[0]
                 t_tax = 0
                 t_count = 0
                 
                 # 找 Tax: 第二大的數，且小於 Amount
                 # 排除像是 2024 (年份) 這樣的噪音? 
                 # Amount 通常很大 (> 10000)
                 
                 potential_taxes = [n for n in nums if n < t_amount]
                 if potential_taxes:
                     t_tax = potential_taxes[0]
                     
                     # 找 Count: 剩下的數中最小的整數
                     potential_counts = [n for n in potential_taxes if n < t_tax]
                     if potential_counts:
                         t_count = potential_counts[-1] # 最小
                     else:
                         # 如果只剩 tax，可能 count 在 amount 和 tax 中間? 不太可能
                         # 或者是 1
                         t_count = 1
                 else:
                     # 只有一個大數
                     pass

                 # 驗證
                 if t_amount > 0:
                     parsed_total["總計"] = {
                         "份數": t_count,
                         "給付總額": t_amount,
                         "扣繳稅額": t_tax
                     }
                     # 默認歸類為非個人 (如果無法區分)
                     parsed_total["非個人"] = parsed_total["總計"]
                     break
        
        return parsed_total

    def _empty_total(self) -> Dict[str, Any]:
        """返回空的合計結構"""
        return {
            "個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0},
            "非個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0},
            "總計": {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
        }

    def parse_footer_info(self) -> Dict[str, Any]:
        """解析頁尾資訊"""
        filing_count = self.extract_field(r"[申中]報次數[:：]\s*(\d+)")
        filing_time = self.extract_field(r"[申中]報時間[:：]\s*([\d/:\s]+)")
        tax_office = self.extract_field(r"財政部臺北國稅局\s*(\S+?)\s*稽徵")

        # 提取退撫金額
        pension_amount = self.extract_field(r"退撫相關法令提[\(（]撥[\)）]繳[\(（]不計入薪資收入課稅[\)）]金額共\s*[\s_＿]*([\d,＿_\s]+)\s*元")
        if not pension_amount:
            pension_amount = self.extract_field(r"不計入薪資收入課稅[\)）]金額共\s*[\s_＿]*([\d,＿_\s]+)\s*元")

        # 清理退撫金額
        if pension_amount:
            pension_amount = pension_amount.replace('＿', '').replace('_', '').replace(' ', '')

        # 提取聯絡人和電話
        contact_person = self.extract_field(r"聯絡人[:：]\s*(\S+)")
        contact_phone = self.extract_field(r"聯絡電話[:：]\s*([\d\-]+)")

        return {
            "聯絡電話": contact_phone,
            "聯絡人": contact_person,
            "印表日期": self.extract_field(r"印表日期[:：]\s*(\S+)"),
            "收件編號": self.extract_field(r"收件編號[:：]\s*(\S+)"),
            "申報次數": filing_count,
            "申報時間": filing_time,
            "稽徵所": tax_office,
            "退撫金額_不計入薪資收入課稅": self.safe_int(pension_amount) if pension_amount else 0
        }

    def parse_single_statement(self) -> Dict[str, Any]:
        """解析單張扣繳憑單 (非清單模式)"""
        # 尋找金額
        # 尋找包含大數字和百分比的行，通常是金額行
        # 格式: 給付總額 ... 扣繳率 ... 扣繳稅額 ... 給付淨額
        amount = 0
        tax = 0
        rate = 0
        
        # 1. 嘗試尋找有 % 的行
        for line in self.lines:
            if "%" in line:
                # 提取所有數字
                nums = re.findall(r'[\d,]+', line)
                clean_nums = [self.safe_int(x) for x in nums if self.safe_int(x) > 0]
                clean_nums.sort(reverse=True)
                
                # 通常最大的是給付總額，第二大是給付淨額，第三大是扣繳稅額
                if len(clean_nums) >= 3:
                    amount = clean_nums[0]
                    # tax 通常是第三大 (Amount > Net > Tax)
                    # 或者是第二大 (如果沒有 Net)
                    # 驗證: Amount - Tax = Net?
                    # or Amount * Rate = Tax?
                    
                    # 嘗試找 Tax
                    # 假設 clean_nums[0] 是總額
                    # 檢查剩餘數字中是否有合理的 Tax
                    possible_taxes = clean_nums[1:]
                    for t in possible_taxes:
                         # 粗略檢查 20% 或 10%
                         if abs(amount * 0.2 - t) < 10 or abs(amount * 0.1 - t) < 10 or abs(amount * 0.15 - t) < 10:
                             tax = t
                             break
                         # 或者如果只有 Amount, Net, Tax，那 Tax 應該是 Amount - Net
                         # 這裡簡單取第三大 (如果是 Amount, Net, Tax)
                         # 如果是 Amount, Tax, Rate...
                    
                    if tax == 0 and len(clean_nums) >= 3:
                         # 盲猜: Amount, Net, Tax
                         if clean_nums[0] > clean_nums[1] > clean_nums[2]:
                             if abs(clean_nums[0] - clean_nums[2] - clean_nums[1]) < 100:
                                 tax = clean_nums[2]
        
        # 如果策略 1 失敗，嘗試尋找最大的兩個數字
        if amount == 0:
             all_nums = []
             for line in self.lines:
                 # 忽略頁尾雜訊
                 if re.search(r"(Copy|備查|本\()", line):
                     continue
                     
                 nums = re.findall(r'[\d,]+', line)
                 all_nums.extend([self.safe_int(x) for x in nums])
             
             all_nums = [n for n in all_nums if n > 1000] # 過濾年份等
             all_nums.sort(reverse=True)
             
             if len(all_nums) >= 2:
                 amount = all_nums[0]
                 # 嘗試找 tax
                 for n in all_nums[1:]:
                     if n < amount:
                         # 檢查常見稅率
                         ratio = n / amount
                         if 0.05 <= ratio <= 0.35: # 5% ~ 35%
                             tax = n
                             break

        # 嘗試識別所得類別
        # 尋找打勾的項目或代號
        income_type = "其他"
        income_code = "UNKNOWN"
        
        # 關鍵字搜尋
        if "權利金" in self.text or "Royalty" in self.text:
            income_type = "權利金"
            income_code = "53"
        elif "薪資" in self.text or "Salary" in self.text:
             income_type = "薪資"
             income_code = "50"
        elif "利息" in self.text or "Interest" in self.text:
             income_type = "利息"
             income_code = "5A"
        elif "租賃" in self.text or "Rental" in self.text:
             income_type = "租賃"
             income_code = "51"
        elif "執行業務" in self.text or "Professional" in self.text:
             income_type = "執行業務報酬"
             income_code = "9A"
             
        # 構建結果
        item = {
            "所得類別": income_type,
            "代號": income_code,
            "個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0},
            "非個人": {"份數": 1, "給付總額": amount, "扣繳稅額": tax}
        }
        
        if amount == 0:
            print("警告：無法在憑單中識別出有效金額，可能是 OCR 識別失敗 (手寫或字體模糊)")
        
        return {
            "基本資訊": self.parse_basic_info(),
            "所得項目": [item],
            "合計": {
                "個人": {"份數": 0, "給付總額": 0, "扣繳稅額": 0},
                "非個人": {"份數": 1, "給付總額": amount, "扣繳稅額": tax},
                "總計": {"份數": 1, "給付總額": amount, "扣繳稅額": tax}
            },
            "其他資訊": self.parse_footer_info()
        }

    def parse(self) -> Dict[str, Any]:
        """執行完整解析"""
        self.extract_text()

        # Debug: Save extracted text
        debug_path = self.pdf_path + ".txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(self.text)
        print(f"DEBUG: Extracted text saved to {debug_path}")

        if not self.text.strip():
            print("警告：無法提取任何文本！")
            if not OCR_AVAILABLE:
                print("提示：安裝 OCR 相關套件以處理圖像型 PDF")
        
        # 檢測是否為單張憑單格式 (KK-9)
        if "非境內居住之個人" in self.text or "Withholding" in self.text:
            self.data = self.parse_single_statement()
            self.data["表單類型"] = "各類所得扣繳暨免扣繳憑單 (非境內居住)"
            self.data["表單編號"] = "KK-Single"
            return self.data

        basic_info = self.parse_basic_info()
        items = self.parse_income_items()
        total = self.parse_total()
        footer = self.parse_footer_info()

        # 勾稽檢查與自動修正
        # 如果識別到了合計，檢查項目總和是否異常大於合計 (通常是重複識別了合計行)
        parsed_total_amount = total["總計"]["給付總額"]
        if parsed_total_amount > 0:
            calc_amount = 0
            for item in items:
                calc_amount += item['個人']['給付總額'] + item['非個人']['給付總額']
            
            # 容許 1 元誤差
            if calc_amount > parsed_total_amount + 1:
                print(f"警告：項目總和 ({calc_amount:,}) 大於 識別合計 ({parsed_total_amount:,})，嘗試自動修正...")
                
                # 策略 1: 檢查是否有單一項目的金額等於合計金額 (這是最常見的錯誤：合計行被當作項目讀取)
                duplicate_found = False
                for i, item in enumerate(items):
                    item_amount = item['個人']['給付總額'] + item['非個人']['給付總額']
                    if abs(item_amount - parsed_total_amount) <= 1:
                        print(f"  -> 移除疑似重複識別的合計行項目: {item['所得類別']} (金額: {item_amount:,})")
                        items.pop(i)
                        duplicate_found = True
                        break
                
                if not duplicate_found:
                     print("  -> 未發現單一重複項目，保留原數據 (請人工確認)")

        # 強制一致性：使用最終的項目總和更新合計 (避免合計行 OCR 錯誤或遺漏)
        calc_total = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
        calc_person = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
        calc_non_person = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}

        for item in items:
            # 累加個人
            p = item["個人"]
            calc_person["份數"] += p["份數"]
            calc_person["給付總額"] += p["給付總額"]
            calc_person["扣繳稅額"] += p["扣繳稅額"]
            
            # 累加非個人
            np = item["非個人"]
            calc_non_person["份數"] += np["份數"]
            calc_non_person["給付總額"] += np["給付總額"]
            calc_non_person["扣繳稅額"] += np["扣繳稅額"]

        calc_total["份數"] = calc_person["份數"] + calc_non_person["份數"]
        calc_total["給付總額"] = calc_person["給付總額"] + calc_non_person["給付總額"]
        calc_total["扣繳稅額"] = calc_person["扣繳稅額"] + calc_non_person["扣繳稅額"]
        
        # 只有當計算出的總額大於0時才覆蓋 (避免清空了原本可能有值的合計)
        if calc_total["給付總額"] > 0:
            total = {
                "個人": calc_person,
                "非個人": calc_non_person,
                "總計": calc_total
            }

        # 如果合計解析失敗 (0)，嘗試從項目累加 (此段邏輯已被上面的強制一致性覆蓋，但保留作為防呆)
        if total["總計"]["給付總額"] == 0:
            calc_total = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
            calc_person = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}
            calc_non_person = {"份數": 0, "給付總額": 0, "扣繳稅額": 0}

            for item in items:
                # 累加個人
                p = item["個人"]
                calc_person["份數"] += p["份數"]
                calc_person["給付總額"] += p["給付總額"]
                calc_person["扣繳稅額"] += p["扣繳稅額"]
                
                # 累加非個人
                np = item["非個人"]
                calc_non_person["份數"] += np["份數"]
                calc_non_person["給付總額"] += np["給付總額"]
                calc_non_person["扣繳稅額"] += np["扣繳稅額"]

            calc_total["份數"] = calc_person["份數"] + calc_non_person["份數"]
            calc_total["給付總額"] = calc_person["給付總額"] + calc_non_person["給付總額"]
            calc_total["扣繳稅額"] = calc_person["扣繳稅額"] + calc_non_person["扣繳稅額"]
            
            if calc_total["給付總額"] > 0:
                total = {
                    "個人": calc_person,
                    "非個人": calc_non_person,
                    "總計": calc_total
                }

        self.data = {
            "表單類型": "各類所得扣繳暨免扣繳憑單申報書",
            "表單編號": "KK-1",
            "基本資訊": basic_info,
            "所得項目": items,
            "合計": total,
            "其他資訊": footer
        }

        return self.data

    def save_json(self, output_path: str):
        """保存為 JSON 文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"JSON 文件已保存到: {output_path}")


def main():
    """主函數"""
    import sys
    
    print("KK Parser Version: 1.0.1")

    if len(sys.argv) < 2:
        print("用法: python parse_kk.py <PDF文件路徑> [輸出JSON路徑]")
        print("示例: python parse_kk.py KK-1.pdf output.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '.json')

    # 檢查文件是否存在
    if not Path(pdf_path).exists():
        print(f"錯誤: 文件不存在 - {pdf_path}")
        sys.exit(1)

    # 解析 PDF
    print(f"正在解析 PDF: {pdf_path}")
    if not OCR_AVAILABLE:
        print("警告：OCR 功能不可用，僅能處理含文本層的 PDF")
        print("安裝方法: pip install pdf2image pytesseract")

    parser = FormKK1ParserV3(pdf_path)
    data = parser.parse()

    # 保存 JSON
    parser.save_json(output_path)

    # 顯示摘要
    print("\n解析摘要:")
    print(f"  扣繳單位: {data['基本資訊']['名稱']}")
    print(f"  統一編號: {data['基本資訊']['統一編號']}")
    print(f"  申報期間: {data['基本資訊']['申報期間']}")
    print(f"  所得項目數: {len(data['所得項目'])}")

    print(f"\n  個人合計:")
    print(f"    份數: {data['合計']['個人']['份數']:,}")
    print(f"    給付總額: {data['合計']['個人']['給付總額']:,} 元")
    print(f"    扣繳稅額: {data['合計']['個人']['扣繳稅額']:,} 元")

    print(f"\n  非個人合計:")
    print(f"    份數: {data['合計']['非個人']['份數']:,}")
    print(f"    給付總額: {data['合計']['非個人']['給付總額']:,} 元")
    print(f"    扣繳稅額: {data['合計']['非個人']['扣繳稅額']:,} 元")

    print(f"\n  總計:")
    print(f"    份數: {data['合計']['總計']['份數']:,}")
    print(f"    給付總額: {data['合計']['總計']['給付總額']:,} 元")
    print(f"    扣繳稅額: {data['合計']['總計']['扣繳稅額']:,} 元")

    # 列出所有所得項目
    if data['所得項目']:
        print(f"\n  所得項目明細:")
        for item in data['所得項目']:
            if item['個人']['給付總額'] > 0:
                print(f"    【個人】{item['所得類別']} ({item['代號']}): {item['個人']['份數']}份, " +
                      f"給付總額 {item['個人']['給付總額']:,}, 扣繳稅額 {item['個人']['扣繳稅額']:,}")
            if item['非個人']['給付總額'] > 0:
                print(f"    【非個人】{item['所得類別']} ({item['代號']}): {item['非個人']['份數']}份, " +
                      f"給付總額 {item['非個人']['給付總額']:,}, 扣繳稅額 {item['非個人']['扣繳稅額']:,}")

    # 顯示退撫金額
    pension_amount = data['其他資訊'].get('退撫金額_不計入薪資收入課稅', 0)
    if pension_amount > 0:
        print(f"\n  退撫金額（不計入薪資收入課稅）: {pension_amount:,} 元")

    print(f"\n✓ 完成!")


if __name__ == "__main__":
    main()