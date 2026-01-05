# Этап сборки
FROM python:3.11-slim AS builder

WORKDIR /app

# Копируем только requirements.txt для кэширования зависимостей
COPY requirements.txt .

# Устанавливаем зависимости в виртуальное окружение
RUN pip install --no-cache-dir --user -r requirements.txt

# Финальный этап
FROM python:3.11-slim

WORKDIR /app

# Копируем установленные зависимости из builder
COPY --from=builder /root/.local /root/.local

# Копируем исходный код
COPY . .

# Добавляем локальные bin в PATH
ENV PATH=/root/.local/bin:$PATH

# Открываем порт
EXPOSE 5954

# Запускаем приложение
CMD ["python", "app.py"]