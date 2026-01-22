#!/usr/bin/env python3
"""
营业人销售额与税额申报书(401) PDF 解析器
自动将 401 表单 PDF 转换为结构化 JSON 格式
"""

import pdfplumber
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional


class Form401Parser:
    """401 表单解析器"""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.text = ""
        self.data = {}

    def extract_text(self):
        """提取 PDF 文本内容"""
        with pdfplumber.open(self.pdf_path) as pdf:
            self.text = ""
            for page in pdf.pages:
                self.text += page.extract_text() + "\n"
        return self.text

    def safe_int(self, value: str) -> int:
        """安全转换为整数，移除逗号和空格"""
        if not value or value.strip() == "":
            return 0
        try:
            # 移除逗号、空格等
            clean_value = re.sub(r'[,\s元]', '', value)
            return int(clean_value) if clean_value else 0
        except ValueError:
            return 0

    def extract_field(self, pattern: str, default: str = "") -> str:
        """提取单个字段"""
        match = re.search(pattern, self.text, re.MULTILINE)
        return match.group(1).strip() if match else default

    def extract_number(self, pattern: str, default: int = 0) -> int:
        """提取数字字段"""
        value = self.extract_field(pattern, "0")
        return self.safe_int(value)

    def parse_basic_info(self) -> Dict[str, Any]:
        """解析基本信息"""
        return {
            "统一编号": self.extract_field(r"統\s*一\s*編\s*號\s*(\d+)"),
            "营业人名称": self.extract_field(r"營業人名\s*稱\s*(.+?)(?:\n|稅)"),
            "税籍编号": self.extract_field(r"稅\s*籍\s*編\s*號\s*(\d+)"),
            "所属年月份": self.extract_field(r"所屬年月份：(.+?)(?:\n|金額單位)"),
            "营业地址": self.extract_field(r"營業地址.*?(\S+?(?:樓|號))"),
            "负责人姓名": self.extract_field(r"負責人姓\s*名\s*(\S+)"),
            "金额单位": "新臺幣元"
        }

    def parse_sales_items(self) -> Dict[str, Any]:
        """解析销项"""
        # 使用正则提取销项各项数据
        # 根据 PDF 实际格式，直接匹配代号后的数值

        return {
            "应税销售额": {
                "三联式发票_电子计算机发票": {
                    "销售额": self.extract_number(r"三\s*聯\s*式[^1]*1\s+(\d[\d,]*)\s+2"),
                    "税额": self.extract_number(r"三\s*聯\s*式[^1]*1\s+\d[\d,]*\s+2\s+(\d[\d,]*)"),
                    "代号": "1-2"
                },
                "收银机发票_三联式_及电子发票": {
                    "销售额": self.extract_number(r"收銀機發票[^5]*5\s+(\d[\d,]*)\s+6"),
                    "税额": self.extract_number(r"收銀機發票[^5]*5\s+\d[\d,]*\s+6\s+(\d[\d,]*)"),
                    "代号": "5-6"
                },
                "二联式发票_收银机发票_二联式": {
                    "销售额": self.extract_number(r"二聯式發票[^9]*9\s+(\d[\d,]*)\s+10"),
                    "税额": self.extract_number(r"二聯式發票[^9]*9\s+\d[\d,]*\s+10\s+(\d[\d,]*)"),
                    "代号": "9-10"
                },
                "免用发票": {
                    "销售额": self.extract_number(r"免\s*用\s*發\s*票[^13]*13\s+(\d[\d,]*)\s+14"),
                    "税额": self.extract_number(r"免\s*用\s*發\s*票[^13]*13\s+\d[\d,]*\s+14\s+(\d[\d,]*)"),
                    "代号": "13-14"
                },
                "减_退回及折让": {
                    "销售额": self.extract_number(r"減\s*:\s*退\s*回\s*及\s*折\s*讓[^17]*17\s+(\d[\d,]*)\s+18"),
                    "税额": self.extract_number(r"減\s*:\s*退\s*回\s*及\s*折\s*讓[^17]*17\s+\d[\d,]*\s+18\s+(\d[\d,]*)"),
                    "代号": "17-18"
                },
                "合计": {
                    "销售额": self.extract_number(r"合\s*計[^21]*21[^(]*\(1\)\s+(\d[\d,]*)\s+22"),
                    "税额": self.extract_number(r"合\s*計[^21]*21[^(]*\(1\)\s+\d[\d,]*\s+22[^(]*\(2\)\s+(\d[\d,]*)"),
                    "代号": "21(1)-22(2)"
                }
            },
            "零税率销售额": {
                "经海关出口免附证明文件者": {
                    "销售额": self.extract_number(r"收銀機發票[^5]*5\s+\d[\d,]*\s+6\s+\d[\d,]*\s+7\s+(\d[\d,]*)"),
                    "代号": "7"
                },
                "非经海关出口应附证明文件者": {
                    "销售额": self.extract_number(r"免\s*用\s*發\s*票[^13]*13\s+\d[\d,]*\s+14\s+\d[\d,]*\s+15\s+(\d[\d,]*)"),
                    "代号": "15"
                },
                "保税区营业人销售": {
                    "销售额": self.extract_number(r"減\s*:\s*退\s*回\s*及\s*折\s*讓[^17]*17\s+\d[\d,]*\s+18\s+\d[\d,]*\s+19\s+(\d[\d,]*)"),
                    "代号": "19"
                },
                "合计": {
                    "销售额": self.extract_number(r"合\s*計[^21]*21[^(]*\(1\)\s+\d[\d,]*\s+22[^(]*\(2\)\s+\d[\d,]*\s+23[^(]*\(3\)\s+(\d[\d,]*)"),
                    "代号": "23(3)"
                }
            },
            "销售额总计": {
                "金额": self.extract_number(r"銷\s*售\s*額\s*總\s*計[^25]*25[^(]*\(7\)\s+(\d[\d,]*)"),
                "代号": "25(7)",
                "内含销售固定资产": self.extract_number(r"內含銷售[^27]*27\s+(\d[\d,]*)"),
                "代号_固定资产": "27"
            }
        }

    def parse_purchase_items(self) -> Dict[str, Any]:
        """解析进项"""
        return {
            "统一发票扣抵联": {
                "进货及费用": {
                    "金额": self.extract_number(r"28\s+(\d[\d,]*)\s+29"),
                    "税额": self.extract_number(r"28\s+\d[\d,]*\s+29\s+(\d[\d,]*)"),
                    "代号": "28-29"
                },
                "固定资产": {
                    "金额": self.extract_number(r"30\s+(\d[\d,]*)\s+31"),
                    "税额": self.extract_number(r"30\s+\d[\d,]*\s+31\s+(\d[\d,]*)"),
                    "代号": "30-31"
                }
            },
            "三联式收银机发票扣抵联及一般税额计算之电子发票": {
                "进货及费用": {
                    "金额": self.extract_number(r"32\s+(\d[\d,]*)\s+33"),
                    "税额": self.extract_number(r"32\s+\d[\d,]*\s+33\s+(\d[\d,]*)"),
                    "代号": "32-33"
                },
                "固定资产": {
                    "金额": self.extract_number(r"34\s+(\d[\d,]*)\s+35"),
                    "税额": self.extract_number(r"34\s+\d[\d,]*\s+35\s+(\d[\d,]*)"),
                    "代号": "34-35"
                }
            },
            "载有税额之其他凭证": {
                "进货及费用": {
                    "金额": self.extract_number(r"36\s+(\d[\d,]*)\s+37"),
                    "税额": self.extract_number(r"36\s+\d[\d,]*\s+37\s+(\d[\d,]*)"),
                    "代号": "36-37"
                },
                "固定资产": {
                    "金额": self.extract_number(r"38\s+(\d[\d,]*)\s+39"),
                    "税额": self.extract_number(r"38\s+\d[\d,]*\s+39\s+(\d[\d,]*)"),
                    "代号": "38-39"
                }
            },
            "海关代征营业税缴纳证扣抵联": {
                "进货及费用": {
                    "金额": self.extract_number(r"進貨及費用\s+78\s+(\d[\d,]*)\s+79"),
                    "税额": self.extract_number(r"進貨及費用\s+78\s+\d[\d,]*\s+79\s+(\d[\d,]*)"),
                    "代号": "78-79"
                },
                "固定资产": {
                    "金额": self.extract_number(r"固\s*定\s*資\s*產\s+80\s+(\d[\d,]*)\s+81"),
                    "税额": self.extract_number(r"固\s*定\s*資\s*產\s+80\s+\d[\d,]*\s+81\s+(\d[\d,]*)"),
                    "代号": "80-81"
                }
            },
            "进项总金额_包括不得扣抵凭证及普通收据": {
                "进货及费用": {
                    "金额": self.extract_number(r"40\s+(\d[\d,]*)\s+41"),
                    "税额": self.extract_number(r"40\s+\d[\d,]*\s+41\s+(\d[\d,]*)"),
                    "代号": "40-41"
                },
                "固定资产": {
                    "金额": self.extract_number(r"42\s+(\d[\d,]*)\s+43"),
                    "税额": self.extract_number(r"42\s+\d[\d,]*\s+43\s+(\d[\d,]*)"),
                    "代号": "42-43"
                }
            },
            "合计": {
                "进货及费用": {
                    "金额": self.extract_number(r"進貨及費用\s+44\s+(\d[\d,]*)\s+45"),
                    "税额": self.extract_number(r"45\s+\(9\)\s+(\d[\d,]*)"),
                    "代号": "44(9)-45"
                },
                "固定资产": {
                    "金额": self.extract_number(r"固\s*定\s*資\s*產\s+46\s+(\d[\d,]*)\s+47"),
                    "税额": self.extract_number(r"47\s+\(10\)\s+(\d[\d,]*)"),
                    "代号": "46(10)-47"
                }
            },
            "进项总金额_含不得扣抵": {
                "金额": self.extract_number(r"48\s+(\d[\d,]*)"),
                "代号": "48"
            },
            "进口免税货物": self.extract_number(r"進\s*口\s*免\s*稅\s*貨\s*物.*?73.*?(\d[\d,]*)"),
            "购买国外劳务": self.extract_number(r"購\s*買\s*國\s*外\s*勞\s*務.*?74.*?(\d[\d,]*)")
        }

    def parse_tax_calculation(self) -> Dict[str, Any]:
        """解析税额计算"""
        return {
            "1_本期销项税额合计": {
                "金额": self.extract_number(r"1\.\s*本期.*?銷項稅額合計.*?101\s+(\d[\d,]*)"),
                "代号": "101",
                "来源": "(2)"
            },
            "7_得扣抵进项税额合计": {
                "金额": self.extract_number(r"7\.\s*得扣抵進項稅額合計.*?107\s+(\d[\d,]*)"),
                "代号": "107",
                "来源": "(9)+(10)"
            },
            "8_上期累积留抵税额": {
                "金额": self.extract_number(r"8\.\s*上期.*?累積留抵稅額.*?108\s+(\d[\d,]*)"),
                "代号": "108"
            },
            "10_小计": {
                "金额": self.extract_number(r"10\.\s*小計.*?110\s+(\d[\d,]*)"),
                "代号": "110",
                "计算": "7+8"
            },
            "11_本期应实缴税额": {
                "金额": self.extract_number(r"11\.\s*本期.*?應實繳稅額.*?111\s+(\d[\d,]*)"),
                "代号": "111",
                "计算": "1-10"
            },
            "12_本期申报留抵税额": {
                "金额": self.extract_number(r"12\.\s*本期.*?申報留抵稅額.*?112\s+(\d[\d,]*)"),
                "代号": "112",
                "计算": "10-1"
            },
            "13_得退税限额合计": {
                "金额": self.extract_number(r"13\.\s*得退稅限額合計.*?113\s+(\d[\d,]*)"),
                "代号": "113",
                "计算": "(3)x5%+(10)"
            },
            "14_本期应退税额": {
                "金额": self.extract_number(r"14\.\s*本期.*?應退稅額.*?114\s+(\d[\d,]*)"),
                "代号": "114",
                "条件": "如12>13则为13"
            },
            "15_本期累积留抵税额": {
                "金额": self.extract_number(r"15\.\s*本期.*?累積留抵稅額.*?115\s+(\d[\d,]*)"),
                "代号": "115",
                "计算": "12-14"
            }
        }

    def parse_filing_info(self) -> Dict[str, Any]:
        """解析申报信息"""
        return {
            "收件编号": self.extract_field(r"收件編號：\s*(\S+)"),
            "申报次数": self.extract_field(r"申報次數：\s*(\S+)"),
            "申报日期": self.extract_field(r"申報日期：\s*(\S+)"),
            "最后异动日期": self.extract_field(r"最後異動日期：\s*(.+?)(?:\n|進銷項)"),
            "制表日期": self.extract_field(r"製表日期：\s*(\S+)"),
            "进销项笔数": self.extract_number(r"進銷項筆數：\s*(\d[\d,]*)"),
            "零税率销售额笔数": self.extract_number(r"零稅率銷售額筆數：\s*(\d[\d,]*)"),
            "使用发票份数": self.extract_number(r"使用發票份數\s+(\d[\d,]*)\s+份")
        }

    def parse(self) -> Dict[str, Any]:
        """执行完整解析"""
        self.extract_text()

        self.data = {
            "基本信息": self.parse_basic_info(),
            "注记栏": {
                "核准按月申报": False,
                "核准合并总缴": {
                    "各单位分别申报": False,
                    "总机构汇总报缴": False
                }
            },
            "销项": self.parse_sales_items(),
            "进项": self.parse_purchase_items(),
            "税额计算": self.parse_tax_calculation(),
            "申报信息": self.parse_filing_info(),
            "统计笔数": {
                "营业人申报固定资产退税清单笔数": self.extract_number(r"營業人申報固定資產.*?退稅清單筆數：\s*(\d+)"),
                "营业人购买旧乘人小汽车及机车进项凭证明细笔数": self.extract_number(r"營業人購買舊乘.*?人小汽車及機車進：.*?項憑證明細筆數.*?(\d+)"),
                "法院拍卖进项资料笔数": self.extract_number(r"法院拍賣進項資料筆數：\s*(\d+)"),
                "已纳税额": self.extract_number(r"已納稅額：\s*(\d[\d,]*)")
            },
            "申办情形": {
                "类型": "自行申报" if "自行申報" in self.text else "委任申报",
                "姓名": self.extract_field(r"姓\s*名\s*(\S+)"),
                "身分证统一编号": "",
                "电话": self.extract_field(r"電\s*話\s*([\d\-#\s]+)"),
                "登录文号": ""
            },
            "备注": [
                "一、本申报书适用专营应税及零税率之营业人填报。",
                "二、如营业人申报当期（月）之销售额包括有免税、特种税额计算销售额者，请改用（403）申报书申报。",
                "三、营业人如有依财政部108年11月15日台财税字第10804629000号令规定进行一次性移转订价调整申报营业税，除跨境受控交易为进口货物外，请另填报『营业税一次性移转订价调整声明书』并检附相关证明文件，併同会计年度最后一期营业税申报。",
                "四、纳税者如有依纳税者权利保护法第7条第8项但书规定，为重要事项陈述者，请另填报「营业税声明事项表」并检附相关证明文件。"
            ]
        }

        return self.data

    def save_json(self, output_path: str):
        """保存为 JSON 文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"JSON 文件已保存到: {output_path}")


def main():
    """主函数"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python parse_401.py <PDF文件路径> [输出JSON路径]")
        print("示例: python parse_401.py 03-04.pdf output.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '.json')

    # 检查文件是否存在
    if not Path(pdf_path).exists():
        print(f"错误: 文件不存在 - {pdf_path}")
        sys.exit(1)

    # 解析 PDF
    print(f"正在解析 PDF: {pdf_path}")
    parser = Form401Parser(pdf_path)
    data = parser.parse()

    # 保存 JSON
    parser.save_json(output_path)

    # 显示摘要
    print("\n解析摘要:")
    print(f"  营业人: {data['基本信息']['营业人名称']}")
    print(f"  统一编号: {data['基本信息']['统一编号']}")
    print(f"  所属期间: {data['基本信息']['所属年月份']}")
    print(f"  应实缴税额: {data['税额计算']['11_本期应实缴税额']['金额']:,} 元")
    print(f"\n✓ 完成!")


if __name__ == "__main__":
    main()
