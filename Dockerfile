FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

RUN useradd --create-home --uid 1000 user
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r /app/requirements.txt
COPY --chown=user:user . /app

USER user
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
