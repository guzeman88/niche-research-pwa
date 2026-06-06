# ── Stage 1: Build frontend ─────────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit 2>/dev/null || npm install
COPY . .
RUN npm run build

# ── Stage 2: Python backend + serve frontend static files ────────────────
FROM python:3.12-slim AS backend
WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend to be served by FastAPI
COPY --from=frontend /app/dist ./static/

# Copy config files into backend context
WORKDIR /app/backend

# Create workspace directory
RUN mkdir -p workspace

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
