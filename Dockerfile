# Dockerfile
# Tax AI OCR 獨立應用程式

FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 建立上傳目錄
RUN mkdir -p /app/uploads/tax_ai_ocr

# 設定環境變數
ENV FLASK_APP=run.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# 暴露 port
EXPOSE 5002

# 啟動命令
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "4", "run:app"]
