FROM python:3.11-alpine
RUN apk add --no-cache docker-cli
WORKDIR /app
COPY app.py .
CMD ["python", "app.py"]
