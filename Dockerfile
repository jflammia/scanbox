FROM python:3.13-slim AS base

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="ScanBox"
LABEL org.opencontainers.image.description="Medical document scanning pipeline"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

# System dependencies for OCR and PDF processing
# ghostscript is required by ocrmypdf >= 17
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    ghostscript \
    poppler-utils \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source and install
COPY pyproject.toml .
COPY scanbox/ scanbox/
COPY static/ static/
RUN pip install --no-cache-dir .

# Create directories for volumes
RUN mkdir -p /app/data /output

# Run as non-root
RUN useradd --create-home scanbox
USER scanbox

ENV PYTHONUNBUFFERED=1
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8090

CMD ["uvicorn", "scanbox.main:app", "--host", "0.0.0.0", "--port", "8090"]
