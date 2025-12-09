# 401 表单 PDF 转 JSON 工具

自动将台湾营业人销售额与税额申报书（401表）PDF 转换为结构化 JSON 格式。

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

### 基本用法

```bash
python parse_401.py 03-04.pdf
```

这会在同一目录下生成 `03-04.json` 文件。

### 指定输出路径

```bash
python parse_401.py 03-04.pdf output/result.json
```

### 批量处理

```bash
# 处理当前目录所有 PDF
for file in *.pdf; do
    python parse_401.py "$file"
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

## 文件说明

- `parse_401.py` - 主要解析脚本
- `template_401.json` - JSON 结构模板示例
- `requirements.txt` - Python 依赖
- `README.md` - 本说明文件

## 进阶使用

### 在 Python 代码中使用

```python
from parse_401 import Form401Parser

# 创建解析器
parser = Form401Parser("03-04.pdf")

# 解析 PDF
data = parser.parse()

# 访问数据
print(f"营业人: {data['基本信息']['营业人名称']}")
print(f"应缴税额: {data['税额计算']['11_本期应实缴税额']['金额']}")

# 保存为 JSON
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
