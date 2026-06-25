# UI image: Streamlit + k8sgpt binary baked in (airgap-friendly).
# Build OUTSIDE airgap (needs internet to fetch k8sgpt + pip), then docker save -> carry in.
FROM python:3.12-slim

# --- k8sgpt binary ---
# Verify/bump version at: https://github.com/k8sgpt-ai/k8sgpt/releases
ARG K8SGPT_VERSION=0.3.48
ARG TARGETARCH=x86_64

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tar \
    && curl -fsSL -o /tmp/k8sgpt.tar.gz \
       "https://github.com/k8sgpt-ai/k8sgpt/releases/download/v${K8SGPT_VERSION}/k8sgpt_Linux_${TARGETARCH}.tar.gz" \
    && tar -xzf /tmp/k8sgpt.tar.gz -C /usr/local/bin k8sgpt \
    && chmod +x /usr/local/bin/k8sgpt \
    && rm /tmp/k8sgpt.tar.gz \
    && apt-get purge -y curl tar && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY runbooks /app/runbooks

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
