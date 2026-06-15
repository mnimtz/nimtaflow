FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    exiftool \
    gosu \
    tzdata \
    libheif-examples \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
# insightface's setup.py needs numpy + Cython available at build time, so
# pre-install them before resolving the full requirements set.
RUN pip install --no-cache-dir "numpy==1.26.4" "cython<3.1"
RUN pip install --no-cache-dir -r requirements.txt
# 4-bit (nf4) quantization so Qwen2.5-VL-3B fits the 8 GB card (~2.5 GB vs 7.5 GB).
# Separate layer → the big requirements install above stays cached.
RUN pip install --no-cache-dir "bitsandbytes==0.43.1"

FROM deps AS final
COPY . .

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run entrypoint as root so it can chown /cache and /config, then drops to appuser
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
