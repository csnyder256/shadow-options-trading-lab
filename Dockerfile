FROM python:3.14-slim AS core
LABEL org.opencontainers.image.source="https://github.com/csnyder256/shadow-options-trading-lab"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/atlas PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /opt/atlas
COPY requirements.txt VERSION ./
RUN pip install --no-cache-dir -r requirements.txt
COPY atlas atlas
COPY scripts scripts
RUN useradd --create-home --uid 10001 atlas && mkdir runtime config && chown atlas:atlas runtime
USER atlas
ENTRYPOINT ["python"]
CMD ["scripts/run_strategy_lab.py", "--help"]

FROM core AS vision
USER root
RUN python -m playwright install --with-deps chromium
USER atlas

FROM core AS runtime
