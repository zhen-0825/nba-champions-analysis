# Hugging Face Space 用的環境設定：裝好 Python 和套件，再啟動 Streamlit 網頁
FROM python:3.11-slim

WORKDIR /app
ENV HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY .streamlit ./.streamlit

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
