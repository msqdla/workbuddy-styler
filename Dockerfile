# 使用自带 Chromium 的官方镜像，省去手动安装浏览器
FROM mcr.microsoft.com/playwright/python:v1.47.2-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8777

CMD ["python3", "app.py"]
