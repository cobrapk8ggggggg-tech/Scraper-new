FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY sites ./sites
COPY worker ./worker
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
CMD ["python", "worker/scrape_worker.py"]
