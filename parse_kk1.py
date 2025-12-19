#!/usr/bin/env python3
"""
扣繳單位稅籍編號扣繳暨免扣繳憑單申報書 (KK-1) PDF 解析器
自動將 KK-1 表單 PDF 轉換為結構化 JSON 格式

注意：此 PDF 為圖像格式，需要使用 OCR 技術提取文本
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


class FormKK1Parser:
    """KK-1 扣繳申報書解析器"""

    def __init__(self, pdf_path: str, use_ocr: bool = True):
        self.pdf_path = pdf_path
        self.text = ""
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
            self.text = self.extract_text_with_ocr()

        return self.text

    def extract_text_with_ocr(self) -> str:
        """使用 OCR 提取文本"""
        try:
            images = convert_from_path(self.pdf_path)
            text = ""
            for i, image in enumerate(images):
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
        if not value or value.strip() == "":
            return 0
        try:
            # 移除逗號、空格等
            clean_value = re.sub(r'[,\s元]', '', value)
            return int(clean_value) if clean_value else 0
        except ValueError:
            return 0

    def extract_field(self, pattern: str, default: str = "") -> str:
        """提取單個字段"""
        match = re.search(pattern, self.text, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else default

    def extract_number(self, pattern: str, default: int = 0) -> int:
        """提取數字字段"""
        value = self.extract_field(pattern, "0")
        return self.safe_int(value)

    def parse_basic_info(self) -> Dict[str, Any]:
        """解析基本信息"""
        # 提取統一編號 - 多種格式嘗試
        receipt_no = self.extract_field(r"統\s*一\s*編\s*號\s*(\d+)")
        if not receipt_no:
            receipt_no = self.extract_field(r"統\s*-\s*編\s*號\s*(\d+)")

        # 提取扣繳單位稅籍編號
        withholding_tax_no = self.extract_field(r"扣繳單位稅籍編號\s*(\d+)")
        if not withholding_tax_no:
            withholding_tax_no = self.extract_field(r"機關\s*(\d+)")

        # 提取名稱
        name = self.extract_field(r"名\s*稱\s*(.+?)(?:\n|台北市|地址)")

        # 提取地址 - 改進正則表達式
        address = self.extract_field(r"地\s*址\s*(.+?)(?:\n|本單位|扣繳義務人)")
        if not address or "稅籍編號" in address:
            # 嘗試直接提取台北市開頭的地址
            address = self.extract_field(r"(台北市.+?(?:樓|號).*?)(?:\n|本單位)")

        # 提取扣繳義務人/負責人
        withholding_agent = self.extract_field(r"負責人[、，]\s*代表人或管理人[（(]簽章[）)]：\s*(\S+)")
        if not withholding_agent:
            withholding_agent = self.extract_field(r"扣繳\s*義務人\s*(.+?)(?:\n|區\s*分|\()")

        # 提取期間
        period = self.extract_field(r"本單位自(\d+年\d+月\d+日至\d+年\d+月\d+日)止")

        # 提取房屋稅籍編號
        house_tax_no = self.extract_field(r"扣繳單位地址之房屋稅籍編號.*?([A-Z]\d+)")

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
        """解析各類所得項目"""
        items = []

        # 定義所得類別及代號
        income_categories = [
            ("薪資", "3"),
            ("機關團體補助費", "21"),
            ("執行機關等獎給", "22"),
            ("國內利息", "4"),
            ("租金", "51"),
            ("權利金", "52"),
            ("8.6年度盈以前年度股利或盈餘", "11"),
            ("8.7年度盈以後年度股利或盈餘", "12"),
            ("其他", "13"),
            ("設按、證券及債券中購借金", "8"),
            ("退職所得", "9"),
            ("財產交易所得", "7"),
            ("外國條件選舉類", "A2"),
            ("外國選舉獲線航空換單", "A3"),
            ("前2項以外之其他所得", "A")
        ]

        for category_name, code in income_categories:
            item = self.parse_income_item(category_name, code)
            if item:
                items.append(item)

        return items

    def parse_income_item(self, category_name: str, code: str) -> Optional[Dict[str, Any]]:
        """解析單個所得項目"""
        # 在文本中尋找該類所得的數據
        # 格式可能是：代號 個人起迄號碼 個人給付總額 個人扣繳稅額 份數 非個人起迄號碼 非個人給付總額 非個人扣繳稅額

        # 嘗試匹配數據行（簡化版，根據實際格式調整）
        # 這裡需要根據實際的 PDF 格式來調整正則表達式

        result = {
            "所得類別": category_name,
            "代號": code,
            "個人": {
                "起迄號碼": "",
                "給付總額": 0,
                "扣繳稅額": 0,
                "份數": 0
            },
            "非個人": {
                "起迄號碼": "",
                "給付總額": 0,
                "扣繳稅額": 0
            }
        }

        # 嘗試找到該代號的數據（這部分需要根據實際格式精細調整）
        # 由於格式複雜，這裡先返回基本結構
        return result

    def parse_table_data(self) -> List[Dict[str, Any]]:
        """解析表格數據（使用 pdfplumber 的表格提取功能）"""
        items = []

        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    # 處理表格數據
                    for row in table:
                        if row and len(row) >= 8:  # 確保有足夠的列
                            # 嘗試識別數據行
                            if self.is_data_row(row):
                                item = self.parse_data_row(row)
                                if item:
                                    items.append(item)

        return items

    def is_data_row(self, row: List[str]) -> bool:
        """判斷是否為數據行"""
        if not row:
            return False

        # 檢查是否包含數字數據
        for cell in row:
            if cell and re.search(r'\d{6,}', cell):  # 包含較長的數字
                return True
        return False

    def parse_data_row(self, row: List[str]) -> Optional[Dict[str, Any]]:
        """解析單行數據"""
        try:
            # 根據實際表格結構解析
            # 這是一個簡化版本，需要根據實際格式調整

            item = {
                "所得類別": row[0] if len(row) > 0 else "",
                "代號": row[1] if len(row) > 1 else "",
                "個人": {},
                "非個人": {}
            }

            return item
        except Exception as e:
            print(f"解析行數據時出錯: {e}")
            return None

    def parse_total(self) -> Dict[str, Any]:
        """解析合計數據"""
        # 在文本中尋找合計行
        # 格式：合 計 個人份數 個人總額 個人稅額 非個人份數 非個人總額 非個人稅額

        # 嘗試匹配完整的合計行（包含個人和非個人）
        total_match = re.search(
            r"合\s*計\s+(\d+)\s+([\d,]+)\s+([\d,]+)\s+(\d+)\s+([\d,]+)\s+([\d,]+)",
            self.text,
            re.DOTALL
        )

        if total_match:
            return {
                "個人": {
                    "份數": self.safe_int(total_match.group(1)),
                    "給付總額": self.safe_int(total_match.group(2)),
                    "扣繳稅額": self.safe_int(total_match.group(3))
                },
                "非個人": {
                    "份數": self.safe_int(total_match.group(4)),
                    "給付總額": self.safe_int(total_match.group(5)),
                    "扣繳稅額": self.safe_int(total_match.group(6))
                },
                "總計": {
                    "份數": self.safe_int(total_match.group(1)) + self.safe_int(total_match.group(4)),
                    "給付總額": self.safe_int(total_match.group(2)) + self.safe_int(total_match.group(5)),
                    "扣繳稅額": self.safe_int(total_match.group(3)) + self.safe_int(total_match.group(6))
                }
            }

        # 如果找不到完整格式，嘗試只找個人部分
        simple_match = re.search(
            r"合\s*計.*?(\d+)\s+([\d,]+)\s+([\d,]+)",
            self.text,
            re.DOTALL
        )

        if simple_match:
            return {
                "個人": {
                    "份數": self.safe_int(simple_match.group(1)),
                    "給付總額": self.safe_int(simple_match.group(2)),
                    "扣繳稅額": self.safe_int(simple_match.group(3))
                },
                "非個人": {
                    "份數": 0,
                    "給付總額": 0,
                    "扣繳稅額": 0
                },
                "總計": {
                    "份數": self.safe_int(simple_match.group(1)),
                    "給付總額": self.safe_int(simple_match.group(2)),
                    "扣繳稅額": self.safe_int(simple_match.group(3))
                }
            }

        return {
            "個人": {
                "份數": 0,
                "給付總額": 0,
                "扣繳稅額": 0
            },
            "非個人": {
                "份數": 0,
                "給付總額": 0,
                "扣繳稅額": 0
            },
            "總計": {
                "份數": 0,
                "給付總額": 0,
                "扣繳稅額": 0
            }
        }

    def parse_footer_info(self) -> Dict[str, Any]:
        """解析頁尾資訊"""
        # 提取申報次數和時間
        filing_count = self.extract_field(r"申報次數：\s*(\d+)")
        filing_time = self.extract_field(r"申報時間：\s*([\d/:\s]+)")

        # 提取稽徵所
        tax_office = self.extract_field(r"財政部臺北國稅局(.+?)稽徵所")

        return {
            "扣繳單位蓋章": "",
            "扣繳義務人簽章": "",
            "聯絡電話": self.extract_field(r"聯絡電話：\s*([\d\-]+)"),
            "聯絡人": self.extract_field(r"聯絡人：\s*(\S+)"),
            "印表日期": self.extract_field(r"印表日期：\s*(\S+)"),
            "收件編號": self.extract_field(r"收件編號：\s*(\S+)"),
            "申報次數": filing_count,
            "申報時間": filing_time,
            "稽徵所": tax_office,
            "截止日期": self.extract_field(r"截止日期：\s*(\S+)")
        }

    def parse_manual_extraction(self) -> List[Dict[str, Any]]:
        """手動提取特定數據（針對複雜格式）"""
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

        for income_name, code in income_types:
            item = self.parse_income_detail(income_name, code)
            if item and (item["個人"]["給付總額"] > 0 or item["非個人"]["給付總額"] > 0):
                items.append(item)

        return items

    def parse_income_detail(self, income_name: str, code: str) -> Optional[Dict[str, Any]]:
        """解析單個所得類別的詳細數據"""
        # 簡化搜尋模式
        simplified_name = income_name.replace(" ", "").replace("　", "")

        # 構建搜尋模式 - 尋找該所得類別的數據行
        # 格式：份數 起迄號碼 給付總額 扣繳稅額
        pattern = rf"{re.escape(simplified_name)}.*?{code}\s+(\d+)\s+([E\d\-]+)\s+([\d,]+)\s+([\d,]+)"

        # 個人部分
        person_match = re.search(pattern, self.text, re.DOTALL)

        person_data = {
            "起迄號碼": "",
            "給付總額": 0,
            "扣繳稅額": 0,
            "份數": 0
        }

        if person_match:
            person_data = {
                "份數": self.safe_int(person_match.group(1)),
                "起迄號碼": person_match.group(2).strip(),
                "給付總額": self.safe_int(person_match.group(3)),
                "扣繳稅額": self.safe_int(person_match.group(4))
            }

        # 非個人部分 - 在表格的右側
        non_person_data = {
            "起迄號碼": "",
            "給付總額": 0,
            "扣繳稅額": 0,
            "份數": 0
        }

        # 嘗試找非個人數據（通常在同一行的後面）
        # 格式可能是：份數 起迄號碼 給付總額 扣繳稅額
        non_person_pattern = rf"{code}\s+\d+\s+[E\d\-]+\s+[\d,]+\s+[\d,]+\s+(\d+)\s+([E\d\-]+)\s+([\d,]+)\s+([\d,]+)"
        non_person_match = re.search(non_person_pattern, self.text, re.DOTALL)

        if non_person_match:
            non_person_data = {
                "份數": self.safe_int(non_person_match.group(1)),
                "起迄號碼": non_person_match.group(2).strip(),
                "給付總額": self.safe_int(non_person_match.group(3)),
                "扣繳稅額": self.safe_int(non_person_match.group(4))
            }

        return {
            "所得類別": income_name,
            "代號": code,
            "個人": person_data,
            "非個人": non_person_data
        }

    def parse(self) -> Dict[str, Any]:
        """執行完整解析"""
        self.extract_text()

        # 手動提取的項目
        manual_items = self.parse_manual_extraction()

        # 解析合計
        total = self.parse_total()

        self.data = {
            "表單類型": "扣繳單位稅籍編號扣繳暨免扣繳憑單申報書",
            "基本資訊": self.parse_basic_info(),
            "所得項目": manual_items,
            "合計": total,
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
        print("用法: python parse_kk1.py <PDF文件路徑> [輸出JSON路徑]")
        print("示例: python parse_kk1.py KK-1.pdf output.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '.json')

    # 檢查文件是否存在
    if not Path(pdf_path).exists():
        print(f"錯誤: 文件不存在 - {pdf_path}")
        sys.exit(1)

    # 解析 PDF
    print(f"正在解析 PDF: {pdf_path}")
    parser = FormKK1Parser(pdf_path)
    data = parser.parse()

    # 保存 JSON
    parser.save_json(output_path)

    # 顯示摘要
    print("\n解析摘要:")
    print(f"  扣繳單位: {data['基本資訊']['名稱']}")
    print(f"  統一編號: {data['基本資訊']['統一編號']}")
    print(f"  申報期間: {data['基本資訊']['申報期間']}")
    print(f"  所得項目數: {len(data['所得項目'])}")

    # 檢查合計的結構
    if '總計' in data['合計']:
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
    else:
        print(f"  合計給付總額: {data['合計'].get('給付總額', 0):,} 元")
        print(f"  合計扣繳稅額: {data['合計'].get('扣繳稅額', 0):,} 元")

    print(f"\n✓ 完成!")


if __name__ == "__main__":
    main()
