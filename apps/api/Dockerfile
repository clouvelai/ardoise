FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV ARDOISE_API_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn ardoise_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
