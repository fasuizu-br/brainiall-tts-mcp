FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastmcp>=2.14.0,<3.0.0" httpx
COPY server.py .
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["python", "server.py"]
