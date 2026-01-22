# Tax AI OCR

稅務憑證 AI 辨識系統 - 獨立版本

## 功能特色

- 支援多種稅務文件類型（401、403、扣繳憑單、股利憑單等）
- Azure Document Intelligence OCR 文字辨識
- Claude / GPT-4 LLM 智能資料提取
- 多使用者權限管理
- Excel 匯出功能
- 背景任務處理（Celery）

## 系統需求

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose（推薦）

## 快速開始

### 方式一：Docker Compose（推薦）

1. 複製環境變數範例：
```bash
cp .env.example .env
```

2. 編輯 `.env` 檔案，填入必要的 API 金鑰

3. 啟動所有服務：
```bash
docker-compose up -d
```

4. 存取應用：http://localhost:5002

### 方式二：本地開發

1. 建立虛擬環境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

2. 安裝依賴：
```bash
pip install -r requirements.txt
```

3. 設定環境變數：
```bash
cp .env.example .env
# 編輯 .env 檔案
```

4. 啟動 PostgreSQL 和 Redis（可用 Docker）：
```bash
docker run -d --name taxai_postgres -e POSTGRES_USER=taxai -e POSTGRES_PASSWORD=taxai_password -e POSTGRES_DB=taxai -p 5432:5432 postgres:15-alpine
docker run -d --name taxai_redis -p 6379:6379 redis:7-alpine
```

5. 初始化資料庫：
```bash
flask db upgrade
```

6. 啟動 Flask 應用：
```bash
python run.py
```

7. 另開終端機，啟動 Celery Worker：
```bash
celery -A celery_app worker --loglevel=info
```

8. 另開終端機，啟動 Celery Beat（排程器）：
```bash
celery -A celery_app beat --loglevel=info
```

## 專案結構

```
TaxAI/
├── app/
│   ├── __init__.py      # Flask 應用工廠
│   ├── models.py        # 資料庫模型
│   ├── routes.py        # 路由定義
│   ├── tasks.py         # Celery 任務
│   ├── services/        # 服務層
│   │   ├── ocr_service.py
│   │   ├── llm_service.py
│   │   └── excel_export_service.py
│   ├── utils/           # 工具函數
│   │   └── pdf_utils.py
│   └── prompts/         # LLM Prompts
│       └── prompts.py
├── templates/           # HTML 模板
├── static/             # 靜態檔案
├── migrations/         # 資料庫遷移
├── uploads/            # 上傳檔案目錄
├── config.py           # 配置檔案
├── celery_app.py       # Celery 應用
├── run.py              # 應用入口點
├── requirements.txt    # Python 依賴
├── Dockerfile          # Docker 映像
├── docker-compose.yml  # Docker Compose 配置
└── .env.example        # 環境變數範例
```

## API 端點

### 認證
- `POST /auth/login` - 登入
- `POST /auth/register` - 註冊
- `GET /auth/logout` - 登出

### 案件管理
- `GET /api/cases` - 列出案件
- `POST /api/cases` - 建立案件
- `GET /api/cases/<id>` - 取得案件詳情
- `DELETE /api/cases/<id>` - 刪除案件

### 工作管理
- `GET /api/jobs` - 列出工作
- `GET /api/jobs/<id>` - 取得工作詳情
- `DELETE /api/jobs/<id>` - 刪除工作
- `PATCH /api/jobs/<id>/result` - 更新工作結果

### 檔案上傳
- `POST /api/upload_files` - 上傳檔案

### 版本管理
- `GET /api/versions` - 列出版本
- `POST /api/versions` - 建立版本
- `GET /api/versions/<id>/download` - 下載 Excel

## 環境變數說明

| 變數名稱 | 說明 | 預設值 |
|---------|------|-------|
| FLASK_ENV | 執行環境 | development |
| SECRET_KEY | Flask 密鑰 | - |
| DATABASE_URL | 資料庫連線 URL | - |
| CELERY_BROKER_URL | Celery Broker URL | redis://localhost:6379/0 |
| AZURE_DI_ENDPOINT | Azure OCR 端點 | - |
| AZURE_DI_KEY | Azure OCR 金鑰 | - |
| ANTHROPIC_API_KEY | Claude API 金鑰 | - |
| OPENAI_API_KEY | OpenAI API 金鑰 | - |

## 授權

MIT License
