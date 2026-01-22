# run.py
# 應用程式入口點

import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(host='0.0.0.0', port=5002, debug=debug)
