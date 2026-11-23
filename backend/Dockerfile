# AWS Lambda container (via Lambda Web Adapter) — also runs anywhere Docker runs.
FROM public.ecr.aws/docker/library/python:3.12-slim
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake the embedding model into the image (Lambda's disk is read-only at runtime)
ENV MODEL_CACHE_DIR=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"
COPY app ./app
COPY scripts ./scripts
ENV AWS_LWA_PORT=8000 AWS_LWA_READINESS_CHECK_PATH=/api/v1/health AWS_LWA_READINESS_CHECK_MIN_UNHEALTHY_STATUS=500 PORT=8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
