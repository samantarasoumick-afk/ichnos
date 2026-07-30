# DatFe backend (FastAPI + SQLAlchemy + Alembic).
#
# Build: docker build -t datafe-backend ./backend
# Run:   see docker-compose.yml at the repo root - this image expects
#        DATABASE_URL, SECRET_KEY, ENCRYPTION_KEY, CORS_ALLOWED_ORIGINS
#        to be provided as environment variables (see .env.example).

FROM python:3.11-slim

WORKDIR /app

# gcc/build-essential + freetds-dev cover pymssql / snowflake-connector
# / scikit-learn in case a prebuilt wheel isn't available for the
# target platform - without these, pip install can fail deep into the
# build with a confusing compiler error instead of a clear one.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        freetds-dev \
        freetds-bin \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
