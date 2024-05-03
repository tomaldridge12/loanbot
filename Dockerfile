FROM python:3.12.3-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/src

CMD ["python", "main.py"]
