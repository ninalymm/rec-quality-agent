# 基础镜像与 pip 源都做成参数：默认官方源，国内网络可用 --build-arg 覆盖
ARG BASE_IMAGE=python:3.10-slim
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 先装依赖，利用层缓存：改代码不用重装
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 只带运行需要的：服务代码 + 评测逻辑 + 数据
COPY app ./app
COPY eval ./eval
COPY data/queries.csv ./data/queries.csv
COPY data/candidates ./data/candidates

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
