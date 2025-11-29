FROM python:3.13

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files inside the container
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "item_manager_api.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]