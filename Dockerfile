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
RUN pip install --upgrade pip --root-user-action=ignore

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt /app/requirements.txt

# Устанавливаем Python-библиотеки с флагом ignore root warning
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# Копируем код приложения
COPY . /app

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Порт для локального теста (не обязателен для polling)
EXPOSE 8080

# Запуск бота
CMD ["python", "main.py"]
