# Полигон скелетной анимации: Meta Animated Drawings + маленькая служба.
# Детектор и позер живут в отдельном контейнере torchserve (см. README).
FROM python:3.8-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git libosmesa6 libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/facebookresearch/AnimatedDrawings.git \
    && pip install --no-cache-dir -e AnimatedDrawings \
    && pip install --no-cache-dir flask==2.3.2 onnxruntime==1.16.3

# контекст сборки — корень репозитория (см. docker-compose.yml)
COPY skeleton/app.py /app/app.py
COPY skeleton/lab.html /app/lab.html
# та же модель вырезания, что на телефоне (U²-Net small, Apache-2.0)
COPY models/u2netp.onnx /app/u2netp.onnx

ENV TORCHSERVE=http://torchserve:8080 \
    PYOPENGL_PLATFORM=osmesa \
    OUT_DIR=/data/skeleton

EXPOSE 8200
CMD ["python", "-u", "app.py"]
