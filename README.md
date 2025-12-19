# 台灣稅務表單 PDF 轉 JSON 工具

自動將台灣稅務表單 PDF 轉換為結構化 JSON 格式。

## 支援表單

- **401 表單**：營業人銷售額與稅額申報書
- **KK-1 表單**：扣繳單位稅籍編號扣繳暨免扣繳憑單申報書（新增）

## 功能特点

- 1:1 提取 PDF 表单所有字段
- 保留表单逻辑结构（销项、进项、税额计算等）
- 支持批量处理多份 PDF
- 自动提取所有数值和文本信息

## 安装

1. 安装 Python 依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### 401 表單解析

```bash
# 基本用法
python parse_401.py 03-04.pdf

# 指定輸出路徑
python parse_401.py 03-04.pdf output/result.json
```

### KK-1 表單解析（新增）

```bash
# 基本用法
python parse_kk1.py KK-1.pdf

# 指定輸出路徑
python parse_kk1.py KK-1.pdf output/kk1_result.json
```

**注意**：KK-1 表單如為圖像格式 PDF，需要安裝 OCR 工具。詳見 [KK-1_README.md](KK-1_README.md)。

### 批量處理

```bash
# 處理當前目錄所有 401 PDF
for file in *-*.pdf; do
    python parse_401.py "$file"
done

# 處理所有 KK-1 PDF
for file in KK-*.pdf; do
    python parse_kk1.py "$file"
done
```

## JSON 结构说明

生成的 JSON 文件按照表单逻辑组织，包含以下主要区块：

```json
{
  "基本信息": {
    "统一编号": "...",
    "营业人名称": "...",
    "税籍编号": "...",
    ...
  },
  "销项": {
    "应税销售额": { ... },
    "零税率销售额": { ... },
    "销售额总计": { ... }
  },
  "进项": {
    "统一发票扣抵联": { ... },
    "三联式收银机发票扣抵联及一般税额计算之电子发票": { ... },
    ...
  },
  "税额计算": {
    "1_本期销项税额合计": { ... },
    "7_得扣抵进项税额合计": { ... },
    "11_本期应实缴税额": { ... },
    ...
  },
  "申报信息": { ... },
  "统计笔数": { ... },
  "申办情形": { ... }
}
```

### 字段说明

- 所有金额字段都以整数形式存储（单位：新台币元）
- 每个税额计算项目都包含：
  - `金额`：实际金额
  - `代号`：表单上的代号
  - `来源` 或 `计算`：数据来源或计算公式

## 示例

查看 `template_401.json` 文件以了解完整的 JSON 结构示例。

## 文件說明

### 401 表單相關
- `parse_401.py` - 401 表單解析腳本
- `template_401.json` - 401 JSON 結構模板示例

### KK-1 表單相關（新增）
- `parse_kk1.py` - KK-1 表單解析腳本
- `KK-1.json` - KK-1 JSON 結構示例（實際數據）
- `KK-1_README.md` - KK-1 詳細說明文件

### 通用文件
- `requirements.txt` - Python 依賴
- `README.md` - 本說明文件

## 進階使用

### 在 Python 程式碼中使用 401 解析器

```python
from parse_401 import Form401Parser

# 創建解析器
parser = Form401Parser("03-04.pdf")

# 解析 PDF
data = parser.parse()

# 訪問數據
print(f"營業人: {data['基本信息']['營業人名稱']}")
print(f"應繳稅額: {data['稅額計算']['11_本期應實繳稅額']['金額']}")

# 保存為 JSON
parser.save_json("output.json")
```

### 在 Python 程式碼中使用 KK-1 解析器（新增）

```python
from parse_kk1 import FormKK1Parser

# 創建解析器
parser = FormKK1Parser("KK-1.pdf")

# 解析 PDF
data = parser.parse()

# 訪問數據
print(f"扣繳單位: {data['基本資訊']['名稱']}")
print(f"合計扣繳稅額: {data['合計']['扣繳稅額']:,} 元")

# 保存為 JSON
parser.save_json("output.json")
```

### 批量处理脚本

```python
import glob
from parse_401 import Form401Parser
from pathlib import Path

# 处理所有 PDF
for pdf_file in glob.glob("*.pdf"):
    parser = Form401Parser(pdf_file)
    data = parser.parse()

    # 生成输出文件名
    output_file = Path(pdf_file).stem + ".json"
    parser.save_json(output_file)

    print(f"✓ {pdf_file} -> {output_file}")
```

## 注意事项

1. PDF 必须是可提取文本的格式（不支持扫描版图片 PDF）
2. 如果是扫描版 PDF，需要先进行 OCR 处理
3. 正则表达式根据标准 401 表单格式编写，如果表单格式有变化可能需要调整

## 疑难排解

### 数据提取不完整

如果发现某些字段没有正确提取：

1. 检查 PDF 是否是标准的 401 表单格式
2. 查看提取的原始文本：`parser.extract_text()`
3. 根据实际格式调整 `parse_401.py` 中的正则表达式

### 依赖安装问题

如果 `pdfplumber` 安装失败，可能需要先安装系统依赖：

```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get install poppler-utils
```

## 技术支持

如有问题或建议，欢迎提出 Issue。
