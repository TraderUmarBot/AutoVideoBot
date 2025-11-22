# Используем официальный Python 3.11 slim образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    git \
    libsndfile1 \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt /app/requirements.txt

# Устанавливаем Python-библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . /app

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Порт для локального теста (не обязателен для polling)
EXPOSE 8080

# Запуск бота
CMD ["python", "main.py"]
