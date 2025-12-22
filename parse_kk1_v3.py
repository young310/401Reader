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
            images = convert_from_path(self.pdf_path)  # 使用默認 DPI 保持表格結構
            text = ""
            for i, image in enumerate(images):
                print(f"正在 OCR 處理第 {i+1}/{len(images)} 頁...")
                # 使用繁體中文 OCR
                page_text = pytesseract.image_to_string(image, lang='chi_tra')
                text += page_text + "\n"
            return text
        except Exception as e:
            print(f"OCR 提取失敗: {e}")
            print("提示：請安裝 pdf2image 和 pytesseract")
            print("  pip install pdf2image pytesseract")
            print("  並安裝 Tesseract OCR 引擎")
            return ""

    def safe_int(self, value: str) -> int:
        """安全轉換為整數，移除逗號和空格"""
        if not value or value.strip() == "" or value.strip() == "-":
            return 0
        try:
            clean_value = re.sub(r'[,\s元]', '', value)
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

    def parse_income_line(self, line: str, code: str, income_name: str) -> Optional[Dict[str, Any]]:
        """解析單行所得數據"""
        # 正則表達式匹配：代號 份數 起迄號碼 給付總額 扣繳稅額
        # 個人部分 - 更寬鬆的匹配以應對 OCR 錯誤
        person_pattern = rf"{code}\s+(\d+)\s*[\|｜]?\s*([0-9A-Z]{{8}}-[0-9A-Z]{{8}})\s*[\|｜]?\s*([\d,]+)\s+([\d,]+|-)"
        person_match = re.search(person_pattern, line)

        person_data = {
            "份數": 0,
            "起迄號碼": "",
            "給付總額": 0,
            "扣繳稅額": 0
        }

        if person_match:
            person_data = {
                "份數": self.safe_int(person_match.group(1)),
                "起迄號碼": person_match.group(2).strip(),
                "給付總額": self.safe_int(person_match.group(3)),
                "扣繳稅額": self.safe_int(person_match.group(4))
            }

        # 非個人部分 - 兩種情況
        # 情況1：個人有數據，非個人在後面
        non_person_pattern1 = rf"{code}\s+\d+\s*[0-9A-Z]{{8}}-[0-9A-Z]{{8}}\s+[\d,]+\s+[\d,\-]+\s+(\d+)\s*[\|｜]?\s*([0-9A-Z]{{8}}-[0-9A-Z]{{8}})\s*[\|｜]?\s*([\d,]+)\s+([\d,]+|-)"
        non_person_match1 = re.search(non_person_pattern1, line)

        # 情況2：個人沒有數據（用 - 表示），非個人直接跟在代號後
        non_person_pattern2 = rf"{code}\s+[-\-]\s+(\d+)\s*[\|｜]?\s*([0-9A-Z]{{8}}-[0-9A-Z]{{8}})\s*[\|｜]?\s*([\d,]+)\s+([\d,]+|-)"
        non_person_match2 = re.search(non_person_pattern2, line)

        non_person_data = {
            "份數": 0,
            "起迄號碼": "",
            "給付總額": 0,
            "扣繳稅額": 0
        }

        if non_person_match1:
            non_person_data = {
                "份數": self.safe_int(non_person_match1.group(1)),
                "起迄號碼": non_person_match1.group(2).strip(),
                "給付總額": self.safe_int(non_person_match1.group(3)),
                "扣繳稅額": self.safe_int(non_person_match1.group(4))
            }
        elif non_person_match2:
            non_person_data = {
                "份數": self.safe_int(non_person_match2.group(1)),
                "起迄號碼": non_person_match2.group(2).strip(),
                "給付總額": self.safe_int(non_person_match2.group(3)),
                "扣繳稅額": self.safe_int(non_person_match2.group(4))
            }

        # 如果兩者都沒有數據，返回 None
        if person_data["給付總額"] == 0 and non_person_data["給付總額"] == 0:
            return None

        return {
            "所得類別": income_name,
            "代號": code,
            "個人": person_data,
            "非個人": non_person_data
        }

    def parse_income_items(self) -> List[Dict[str, Any]]:
        """解析所有所得項目"""
        items = []

        # 定義所有所得類別
        income_types = [
            ("薪資", "3"),
            ("稿費等項", "21"),
            ("執行業務報酬", "22"),
            ("利息", "4"),
            ("租賃", "51"),
            ("權利金", "52"),
            ("８６年度或以前年度股利或盈餘", "11"),
            ("８７年度或以後年度股利或盈餘", "12"),
            ("其他", "13"),
            ("競技、競賽及機會中獎獎金", "8"),
            ("退職所得", "9"),
            ("財產交易所得", "7"),
            ("外國營利事業跨境銷售電子勞務所得", "A2"),
            ("外國營利事業取得勞務報酬或營業利潤", "A3"),
            ("外國營利事業適用所得稅法第25條所得", "A4"),
            ("外國營利事業適用所得稅法第26條所得", "A5"),
            ("前4項以外之其他所得", "A")
        ]

        # 遍歷所有行，查找包含起迄號碼的行
        for line in self.lines:
            # 更寬鬆的起迄號碼匹配，考慮 OCR 錯誤
            if re.search(r'[0-9A-Z]{8}-[0-9A-Z]{8}', line):
                # 對每個所得類別進行匹配
                for income_name, code in income_types:
                    # 檢查這一行是否包含該代號
                    if re.search(rf'\|?{code}\s+', line):
                        # 嘗試解析這一行
                        item = self.parse_income_line(line, code, income_name)
                        if item:
                            # 檢查是否已經有這個代號的項目
                            existing_item = next((x for x in items if x['代號'] == code), None)
                            if existing_item:
                                # 合併數據
                                if item['個人']['給付總額'] > 0 and existing_item['個人']['給付總額'] == 0:
                                    existing_item['個人'] = item['個人']
                                if item['非個人']['給付總額'] > 0 and existing_item['非個人']['給付總額'] == 0:
                                    existing_item['非個人'] = item['非個人']
                            else:
                                items.append(item)
                            break

        return items

    def parse_total(self) -> Dict[str, Any]:
        """解析合計數據"""
        # 找到合計行 - 處理 OCR 可能的錯誤
        total_line = ""
        for line in self.lines:
            if re.search(r"合\s*[計討訐]", line):  # OCR 可能把"計"識別成其他字
                total_line = line
                break

        if not total_line:
            return self._empty_total()

        # 解析合計數據：合計 個人份數 個人總額 個人稅額 非個人份數 非個人總額 非個人稅額
        # 更寬鬆的匹配模式
        total_pattern = r"合\s*[計討訐]\s+(\d+)\s+([\d,]+)\s*[\|｜]?.*?\s*([\d,]+)\s+(\d+)\s+([\d,]+)\s+([\d,]+)"
        total_match = re.search(total_pattern, total_line)

        if total_match:
            person_count = self.safe_int(total_match.group(1))
            person_amount = self.safe_int(total_match.group(2))
            person_tax = self.safe_int(total_match.group(3))
            non_person_count = self.safe_int(total_match.group(4))
            non_person_amount = self.safe_int(total_match.group(5))
            non_person_tax = self.safe_int(total_match.group(6))

            return {
                "個人": {
                    "份數": person_count,
                    "給付總額": person_amount,
                    "扣繳稅額": person_tax
                },
                "非個人": {
                    "份數": non_person_count,
                    "給付總額": non_person_amount,
                    "扣繳稅額": non_person_tax
                },
                "總計": {
                    "份數": person_count + non_person_count,
                    "給付總額": person_amount + non_person_amount,
                    "扣繳稅額": person_tax + non_person_tax
                }
            }

        return self._empty_total()

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

    def parse(self) -> Dict[str, Any]:
        """執行完整解析"""
        self.extract_text()

        if not self.text.strip():
            print("警告：無法提取任何文本！")
            if not OCR_AVAILABLE:
                print("提示：安裝 OCR 相關套件以處理圖像型 PDF")

        self.data = {
            "表單類型": "各類所得扣繳暨免扣繳憑單申報書",
            "表單編號": "KK-1",
            "基本資訊": self.parse_basic_info(),
            "所得項目": self.parse_income_items(),
            "合計": self.parse_total(),
            "其他資訊": self.parse_footer_info()
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
        print("用法: python parse_kk1_v3.py <PDF文件路徑> [輸出JSON路徑]")
        print("示例: python parse_kk1_v3.py KK-1.pdf output.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '_v3.json')

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
