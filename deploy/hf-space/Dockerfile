# Hugging Face Space (Docker SDK). Build context = the backend folder + this Dockerfile (staged by deploy_hf.py).
FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV MODEL_CACHE_DIR=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')" && chmod -R a+rX /opt/models
COPY app ./app
COPY scripts ./scripts
RUN chown -R user:user /app
USER user
ENV PORT=7860
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
