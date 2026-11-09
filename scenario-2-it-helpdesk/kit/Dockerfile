# The agent app (FastAPI on port 8000). The simulated helpdesk API has its own image: services/Dockerfile.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Same pins as requirements.txt, only what the app needs (no gradio, no langgraph).
# pymupdf reads the two PDF documents; mcp starts services/helpdesk_mcp.py as a subprocess.
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.52.1 httpx==0.28.1 mcp==1.28.1 \
    pydantic==2.12.5 pydantic-settings==2.14.2 PyYAML==6.0.3 pymupdf==1.28.2 \
    python-dotenv==1.2.4 numpy==2.5.4 openai==2.52.0

COPY app/ /app/app/
COPY services/ /app/services/
COPY dataset/ /app/dataset/
COPY ui/ /app/ui/

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
