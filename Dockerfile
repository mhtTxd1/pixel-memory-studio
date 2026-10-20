FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md requirements.lock.txt ./
COPY pixel_avatar ./pixel_avatar
RUN pip install --no-cache-dir -r requirements.lock.txt && pip install --no-cache-dir --no-deps . && useradd --create-home avatar && mkdir /app/data && chown avatar:avatar /app/data
USER avatar
EXPOSE 8000
CMD ["uvicorn", "pixel_avatar.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
