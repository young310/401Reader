#!/usr/bin/env python3
"""
營業人銷售額與稅額申報書(403) PDF 解析器
適用於兼營免稅、特種稅額計算之營業人
支持 OCR 識別（針對圖片型 PDF）
V4: 替換 OCR 引擎為 PaddleOCR 以提升識別率
"""

import pdfplumber
import re
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

# 設置日誌級別以抑制 PaddleOCR 的大量輸出
# logging.getLogger("ppocr").setLevel(logging.ERROR)

try:
    from pdf2image import convert_from_path
    from paddleocr import PaddleOCR
    import numpy as np
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class Form403Parser:
    """403 表單解析器 (PaddleOCR 版)"""

    def __init__(self, pdf_path: str, use_ocr: bool = True):
        self.pdf_path = pdf_path
        self.text = ""
        self.lines = []
        self.data = {}
        self.use_ocr = use_ocr and OCR_AVAILABLE
        self.ocr_engine = None

    def _init_ocr(self):
        """延遲初始化 PaddleOCR，避免不需 OCR 時載入模型"""
        if self.ocr_engine is None and self.use_ocr:
            print("正在初始化 PaddleOCR 引擎 (這可能需要一點時間)...")
            try:
                # 嘗試使用新參數，移除不兼容的 show_log
                self.ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch')
            except Exception as e:
                print(f"PaddleOCR 初始化失敗: {e}")
                self.ocr_engine = None

    def extract_text(self):
        """提取 PDF 文本內容 (混合模式)"""
        full_text = ""
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    
                    # 檢查該頁是否為圖片 (文本極少)
                    if (not page_text or len(page_text.strip()) < 50) and self.use_ocr:
                        print(f"第 {i+1} 頁無文本層，嘗試 PaddleOCR...")
                        ocr_text = self.ocr_page(i + 1)
                        full_text += ocr_text + "\n"
                    else:
                        full_text += (page_text or "") + "\n"
                        
        except Exception as e:
            print(f"PDF 讀取錯誤: {e}")
            # 如果 pdfplumber 失敗，嘗試全檔 OCR
            if self.use_ocr:
                full_text = self.extract_text_with_ocr()

        self.text = full_text
        self.lines = self.text.split('\n')
        
        # Debug: Save text
        debug_output_path = self.pdf_path + "_debug.txt"
        with open(debug_output_path, "w", encoding="utf-8") as f:
            f.write(self.text)
        print(f"原始識別文本已保存至: {debug_output_path}")
            
        return self.text

    def ocr_page(self, page_number: int) -> str:
        """對單頁進行 OCR"""
        if not self.use_ocr:
            return ""
        
        self._init_ocr()
        try:
            # 轉換 PDF 頁面為圖片
            images = convert_from_path(self.pdf_path, first_page=page_number, last_page=page_number, dpi=300)
            if not images:
                return ""
            
            image = images[0].convert('RGB')
            # Convert PIL image to numpy array for PaddleOCR
            img_np = np.array(image)
            
            # 移除 cls=True 參數
            result = self.ocr_engine.ocr(img_np)
            
            if not result:
                return ""
                
            lines_list = []
            
            # 處理 PaddleOCR 新版返回字典結構的情況 (PaddleX pipeline)
            # result 是一個列表，通常 result[0] 是第一張圖的結果
            first_item = result[0]
            
            texts = None
            boxes = None
            scores = None
            
            # 1. 優先嘗試轉換為 dict (處理 OCRResult 對象)
            try:
                d = dict(first_item)
                texts = d.get('rec_texts')
                boxes = d.get('dt_polys')
                scores = d.get('rec_scores')
            except Exception:
                pass
            
            # 2. 如果轉換失敗或數據為空，嘗試屬性訪問
            if texts is None:
                if hasattr(first_item, 'rec_texts'):
                    texts = getattr(first_item, 'rec_texts', None)
                    boxes = getattr(first_item, 'dt_polys', None)
                    scores = getattr(first_item, 'rec_scores', None)

            if texts is not None and boxes is not None:
                # print(f"DEBUG: Found {len(texts)} texts in OCRResult")
                if scores is None:
                    scores = [1.0] * len(texts)
                    
                for box, text, score in zip(boxes, texts, scores):
                    if hasattr(box, 'tolist'):
                        box = box.tolist()
                    lines_list.append([box, (text, score)])
                    
            elif isinstance(first_item, list):
                 # 舊版結構: [[line...]] 或 [line...]
                 # 如果 first_item 是 [box, (text, score)]，說明 result 本身就是 lines_list
                 if len(first_item) > 0 and isinstance(first_item[0], list) and len(first_item[0]) == 4:
                     lines_list = result
                 elif len(first_item) > 0:
                     lines_list = first_item
            
            if not lines_list:
                print(f"PaddleOCR 解析數據提取失敗，Result type: {type(result[0])}")
                return ""

            lines = []
            current_line = []
            last_y = -1
            
            # 對結果按 Y 坐標排序
            try:
                res = sorted(lines_list, key=lambda x: x[0][0][1])
            except Exception as e:
                print(f"排序失敗: {e}")
                res = lines_list # 放棄排序
            
            for line_info in res:
                if not isinstance(line_info, list) or len(line_info) < 2:
                    continue
                
                box = line_info[0]
                text = line_info[1][0]
                
                y_coord = box[0][1] # Top-Left Y
                
                # 如果是第一行，或與上一行的 Y 差距超過一定閾值 (例如 10 像素)，則視為新行
                if last_y == -1:
                    current_line.append(text)
                    last_y = y_coord
                elif abs(y_coord - last_y) < 15: # 閾值可調整
                    current_line.append(text)
                else:
                    lines.append(" ".join(current_line))
                    current_line = [text]
                    last_y = y_coord
            
            if current_line:
                lines.append(" ".join(current_line))
                
            return "\n".join(lines)

        except Exception as e:
            print(f"PaddleOCR 頁面 {page_number} 失敗: {e}")
            import traceback
            traceback.print_exc()
        return ""

    def extract_text_with_ocr(self) -> str:
        """全檔 OCR (備用)"""
        full_text = ""
        # 獲取總頁數
        try:
            # 簡單讀取一次獲取頁數，或直接循環
            from pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(self.pdf_path)
            pages = info.get('Pages', 1)
            
            for i in range(1, int(pages) + 1):
                print(f"正在 PaddleOCR 處理第 {i}/{pages} 頁...")
                full_text += self.ocr_page(i) + "\n"
                
        except Exception as e:
            print(f"全檔 OCR 失敗: {e}")
            
        return full_text

    def safe_int(self, value: str) -> int:
        """安全轉換為整數"""
        if not value:
            return 0
        try:
            # 移除常見噪音字符，保留數字
            clean_value = re.sub(r'[^\d]', '', value)
            return int(clean_value) if clean_value else 0
        except ValueError:
            return 0

    def extract_field(self, pattern: str, default: str = "") -> str:
        """提取單個字段"""
        match = re.search(pattern, self.text, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else default
    
    def extract_number(self, pattern: str, text_source: str = None) -> int:
        """提取數字"""
        source = text_source if text_source else self.text
        match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
        if match:
            return self.safe_int(match.group(1))
        return 0

    def parse_basic_info(self) -> Dict[str, Any]:
        """解析基本信息"""
        unified_no = ""
        tax_id = ""
        name = ""
        period = ""
        
        header_lines = self.lines[:30]
        header_text = "\n".join(header_lines)
        
        # 統一編號
        u_match = re.search(r"統\s*一\s*.*?\s+(\d{8})\b", header_text)
        if u_match:
            unified_no = u_match.group(1)
        else:
             candidates = re.findall(r'\b\d{8}\b', header_text)
             for cand in candidates:
                 if not cand.startswith("112") and not cand.startswith("202"):
                     unified_no = cand
                     break

        # 稅籍編號
        t_match = re.search(r"稅\s*籍\s*.*?\s+(\d{9})\b", header_text)
        if t_match:
            tax_id = t_match.group(1)
        else:
            candidates = re.findall(r'\b\d{9}\b', header_text)
            if candidates:
                tax_id = candidates[0]

        # 名稱
        n_match = re.search(r"營業人名\s*稱\s*(.+?)(?:\n|112|統一)", header_text)
        if n_match:
            name = n_match.group(1).strip()
        else:
            for line in header_lines:
                if "股份有限公司" in line or "有限公司" in line:
                    clean = re.sub(r"營業人名\s*稱", "", line).strip()
                    name = clean
                    break

        # 所屬年月
        p_match = re.search(r"(\d+\s*年\s*\d+\s*月)", header_text)
        if p_match:
            period = p_match.group(1)

        return {
            "統一編號": unified_no,
            "營業人名稱": name,
            "稅籍編號": tax_id,
            "所屬年月份": period,
            "營業地址": self.extract_field(r"營業地址\s*(.+?)(?:\n|負責人)"),
            "負責人姓名": self.extract_field(r"負責人姓\s*名\s*(\S+)")
        }

    def parse_sales_items(self) -> Dict[str, Any]:
        """解析銷項"""
        s1_amt = s1_tax = 0 
        s5_amt = s5_tax = 0 
        s9_amt = s9_tax = 0 
        ret_amt = ret_tax = 0 
        total_taxable_amt = total_taxable_tax = 0 
        
        zero_customs = 0 
        zero_non_customs = 0 
        zero_bonded = 0
        zero_total = 0 
        
        exempt_amt = 0 
        special_amt = 0 
        grand_total = 0 
        
        in_purchase_section = False

        for line in self.lines:
            clean_line = line.replace(" ", "")
            nums = re.findall(r'[\d,]+', line)
            vals = [self.safe_int(x) for x in nums if self.safe_int(x) > 100] 
            
            if "進項" in line or "扣抵聯" in line or "得扣抵" in line or "進貨及費用" in line:
                in_purchase_section = True
            
            # 應稅項目
            if "三聯式" in line or "電子" in line or "收銀機" in line or "發票" in line:
                if in_purchase_section:
                    continue
                    
                if "零稅率" in line or "免稅" in line or "固定資產" in line:
                    continue
                
                if len(vals) >= 2:
                    amt, tax = vals[0], vals[1]
                    if 0.04 < tax / amt < 0.06:
                        if "三聯式" in line and "計算機" in line:
                            s1_amt, s1_tax = amt, tax
                        elif "收銀機" in line or "電子發票" in line or "三隊式" in line:
                            s5_amt, s5_tax = amt, tax
                        elif "二聯式" in line:
                            s9_amt, s9_tax = amt, tax

            # 退回
            if "退" in line and "折讓" in line and not in_purchase_section:
                 if len(vals) >= 2:
                     ret_amt, ret_tax = vals[0], vals[1]

            # 合計 (應稅)
            if "合計" in line and not in_purchase_section and len(vals) >= 2:
                 if vals[1] > 0 and 0.04 < vals[1] / vals[0] < 0.06:
                     total_taxable_amt, total_taxable_tax = vals[0], vals[1]
            
            # 零稅率 - 代號匹配
            
            # 代號 7 (經海關)
            if zero_customs == 0:
                match_7 = re.search(r'(?:^|[^\d])7\s+([\d,]{4,})', line)
                if match_7:
                    if "應稅" not in line and "三聯" not in line and "進項" not in line:
                        zero_customs = self.safe_int(match_7.group(1))

            # 代號 15 (非經海關)
            if zero_non_customs == 0:
                match_15 = re.search(r'(?:^|[^\d])15\s+([\d,]{4,})', line)
                if match_15:
                    zero_non_customs = self.safe_int(match_15.group(1))
            
            # 代號 19 (保稅區)
            if "保稅區" in line or "19" in line:
                match_19 = re.search(r'(?:^|[^\d])19\s+.*?([\d,]{4,})', line)
                if match_19:
                    zero_bonded = self.safe_int(match_19.group(1))
                elif "保稅區" in line and len(vals) >= 1:
                    zero_bonded = vals[0]

            # 代號 23 (零稅率合計)
            if zero_total == 0:
                match_23 = re.search(r'(?:^|[^\d])23\s+.*?([\d,]{8,})', line)
                if match_23:
                    zero_total = self.safe_int(match_23.group(1))
                else:
                    match_23_alt = re.search(r'23\s*\(3\)\s*.*?([\d,]{8,})', line)
                    if match_23_alt:
                        zero_total = self.safe_int(match_23_alt.group(1))

            # 免稅
            if "免稅銷售額" in clean_line and len(vals) >= 1:
                exempt_amt = vals[0]

            # 特種
            if "特種稅額" in clean_line and len(vals) >= 1:
                special_amt = vals[0]
                
            # 總計
            if "銷售額總計" in clean_line and len(vals) >= 1:
                grand_total = vals[0]

        # 補全
        if zero_bonded == 0:
             match_19_global = re.search(r'(?:^|[^\d])19\s+.*?([\d,]{5,})', self.text)
             if match_19_global:
                 try:
                    zero_bonded = self.safe_int(match_19_global.group(1))
                 except Exception:
                    pass

        if total_taxable_amt == 0:
            total_taxable_amt = s1_amt + s5_amt + s9_amt - ret_amt
            total_taxable_tax = s1_tax + s5_tax + s9_tax - ret_tax
            
        if zero_total == 0:
            zero_total = zero_customs + zero_non_customs + zero_bonded
            
        if grand_total == 0:
            grand_total = total_taxable_amt + zero_total + exempt_amt + special_amt

        return {
            "應稅": {
                "三聯式發票_電子計算機發票": {"銷售額": s1_amt, "稅額": s1_tax, "代號": "1-2"},
                "三聯式收銀機_電子發票": {"銷售額": s5_amt, "稅額": s5_tax, "代號": "5-6"},
                "二聯式收銀機_二聯式發票": {"銷售額": s9_amt, "稅額": s9_tax, "代號": "9-10"},
                "減_退回及折讓": {"銷售額": ret_amt, "稅額": ret_tax, "代號": "17-18"},
                "合計": {"銷售額": total_taxable_amt, "稅額": total_taxable_tax}
            },
            "零稅率": {
                "經海關出口": {"銷售額": zero_customs, "代號": "7"},
                "非經海關出口": {"銷售額": zero_non_customs, "代號": "15"},
                "保稅區營業人": {"銷售額": zero_bonded, "代號": "19"},
                "合計": {"銷售額": zero_total}
            },
            "免稅": {
                "銷售額合計": exempt_amt
            },
            "特種稅額": {
                "銷售額合計": special_amt
            },
            "銷售額總計": {
                "金額": grand_total
            }
        }

    def parse_purchase_items(self) -> Dict[str, Any]:
        """解析進項"""
        p1_amt = p1_tax = 0 
        p1_fixed_amt = p1_fixed_tax = 0 
        p2_amt = p2_tax = 0 
        p2_fixed_amt = p2_fixed_tax = 0 
        p3_amt = p3_tax = 0 
        total_input_amt = 0 
        
        for line in self.lines:
            clean_line = line.replace(" ", "")
            nums = re.findall(r'[\d,]+', line)
            vals = [self.safe_int(x) for x in nums if self.safe_int(x) > 100]
            
            if "統一發票扣抵" in line or "統一發票" in line:
                if len(vals) >= 2:
                    if "固定資產" in line:
                         p1_fixed_amt, p1_fixed_tax = vals[0], vals[1]
                    elif p1_amt == 0: 
                         p1_amt, p1_tax = vals[0], vals[1]

            if "三聯式收銀機" in line:
                 if len(vals) >= 2:
                     if "固定資產" in line:
                         p2_fixed_amt, p2_fixed_tax = vals[0], vals[1]
                     elif p2_amt == 0:
                         p2_amt, p2_tax = vals[0], vals[1]

            if "海關代" in line and len(vals) >= 2:
                p3_amt, p3_tax = vals[0], vals[1]

            if "進項總金額" in clean_line and len(vals) >= 1:
                total_input_amt = vals[0]
                
        return {
            "統一發票扣抵聯": {
                "進貨及費用": {"金額": p1_amt, "稅額": p1_tax},
                "固定資產": {"金額": p1_fixed_amt, "稅額": p1_fixed_tax}
            },
            "三聯式收銀機": {
                "進貨及費用": {"金額": p2_amt, "稅額": p2_tax},
                "固定資產": {"金額": p2_fixed_amt, "稅額": p2_fixed_tax}
            },
            "海關代徵": {
                "金額": p3_amt, "稅額": p3_tax
            },
            "進項總金額": total_input_amt
        }

    def parse_tax_calculation(self) -> Dict[str, Any]:
        """解析稅額計算"""
        tax_sales_total = 0 
        tax_input_deductible = 0 
        prev_remain = 0 
        tax_payable = 0 
        remain_current = 0 
        refund_limit = 0 
        refund_current = 0 
        remain_final = 0 
        
        for line in self.lines:
            clean_line = line.replace(" ", "")
            nums = re.findall(r'[\d,]+', line)
            vals = [self.safe_int(x) for x in nums if self.safe_int(x) > 0]
            if not vals:
                continue
                
            last_val = vals[-1]
            
            if "銷項稅額合" in clean_line or "銷項稅額" in clean_line:
                if "本期" in clean_line:
                    tax_sales_total = last_val
            
            if "小計" in clean_line and ("7" in line or "8" in line):
                if last_val > 1000:
                    tax_input_deductible = last_val
            
            if "得扣抵進項" in clean_line and tax_input_deductible == 0:
                 if last_val > 1000:
                     tax_input_deductible = last_val
                     
            if "累積留抵" in clean_line and "上期" in clean_line:
                prev_remain = last_val if last_val > 0 else 0
                
            if "應實繳" in clean_line:
                tax_payable = last_val
                
            if "申報留抵" in clean_line or "中報留" in clean_line:
                remain_current = last_val
                
            if "得退稅" in clean_line or "限額" in clean_line:
                 if last_val > 1000:
                     refund_limit = last_val
                     
            if "應退稅額" in clean_line and "本期" in clean_line:
                refund_current = last_val
                
            if "累積留抵" in clean_line and "本期" in clean_line:
                remain_final = last_val

        return {
            "本期銷項稅額合計": tax_sales_total,
            "得扣抵進項稅額合計": tax_input_deductible,
            "上期累積留抵稅額": prev_remain,
            "本期應實繳稅額": tax_payable,
            "本期申報留抵稅額": remain_current,
            "得退稅限額合計": refund_limit,
            "本期應退稅額": refund_current,
            "本期累積留抵稅額": remain_final
        }

    def parse(self) -> Dict[str, Any]:
        """執行完整解析"""
        self.extract_text()
        
        self.data = {
            "表單類型": "營業人銷售額與稅額申報書(403)",
            "基本信息": self.parse_basic_info(),
            "銷項": self.parse_sales_items(),
            "進項": self.parse_purchase_items(),
            "稅額計算": self.parse_tax_calculation(),
            "備註": "本解析器基於 PaddleOCR 技術，請務必人工核對數字。"
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

    if len(sys.argv) < 2:
        print("用法: python parse_403.py <PDF文件路徑> [輸出JSON路徑]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '.json')

    if not Path(pdf_path).exists():
        print(f"錯誤: 文件不存在 - {pdf_path}")
        sys.exit(1)

    if not OCR_AVAILABLE:
        print("警告: PaddleOCR 未安裝或導入失敗，請安裝: pip install paddlepaddle paddleocr opencv-python-headless")
        # 繼續執行，但 OCR 功能將不可用

    print(f"正在解析 PDF: {pdf_path}")
    parser = Form403Parser(pdf_path)
    data = parser.parse()

    parser.save_json(output_path)
    
    print("\n解析摘要:")
    print(f"  營業人: {data['基本信息']['營業人名稱']}")
    print(f"  統一編號: {data['基本信息']['統一編號']}")
    print(f"  所屬期間: {data['基本信息']['所屬年月份']}")
    print(f"  銷項總額: {data['銷項']['銷售額總計']['金額']:,} 元")
    print(f"  應納/退稅額: {data['稅額計算']['本期應實繳稅額'] + data['稅額計算']['本期應退稅額']:,} 元")


if __name__ == "__main__":
    main()
