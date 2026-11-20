FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && mkdir -p instance && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "gunicorn app:app --workers 2 --bind 0.0.0.0:${PORT}"]
