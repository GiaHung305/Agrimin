FROM python:3.12-slim@sha256:3ecf5ebe01fef4b6e81be34511fb40bf378ea7fd81ab215ba15b2775ef85413d

WORKDIR /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
