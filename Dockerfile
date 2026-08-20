FROM node:24-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-openai.txt /app/backend/requirements-openai.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt -r /app/backend/requirements-openai.txt
COPY backend /app/backend
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
COPY data /app/data

ENV PYTHONPATH=/app/backend
ENV AUCTION_AGENT_MODE=mock
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
