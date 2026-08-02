# Orca Data Warehouse - Hosted Services Deployment Guide

This guide provides step-by-step instructions to recreate the complete serverless hosted stack for Orca on **Google Cloud Run**, **Cloudflare Workers**, and **GitHub Pages** under `orca-datawarehouse.dev`.

---

## 1. Architectural Overview

```
                           +----------------------------------------+
                           |  Cloudflare Worker Router              |
                           |  (orca-datawarehouse.dev/*)            |
                           +-------------------+--------------------+
                                               |
        +----------------------+---------------+-----------------------+----------------------+
        |                      |                                       |                      |
        v                      v                                       v                      v
/analytics/*            /orchestration/*                         /transformation/*      /dashboards/*
Malloy Publisher        Dagster Web UI                           dbt Documentation      Streamlit Dashboard
(GCP Cloud Run)         (GCP Cloud Run)                          (GitHub Pages)         (Embedded Iframe)
        |                      |
        +----------+-----------+
                   |
                   v
     Frozen DuckLake over HTTP
(GitHub Raw: storage/orca.ducklake)
```

---

## 2. Hosted Services & Routes

| Route | Service | Backend Technology | Access Mode |
| :--- | :--- | :--- | :--- |
| **`/analytics/`** | Malloy Publisher | GCP Cloud Run (`orca-malloy`) | Interactive dashboards & metrics |
| **`/orchestration/`** | Dagster Web UI | GCP Cloud Run (`orca-dagster`) | Read-only asset graph & logs |
| **`/transformation/`** | dbt Documentation | GitHub Pages (`mathisdrn.github.io/orca`) | Static lineage & schema docs |
| **`/dashboards/`** | Streamlit App | Streamlit Cloud (`orca-dashboard.streamlit.app`) | Fullscreen iframe wrapper |

---

## 3. Directory Structure (`deployment/`)

```
deployment/
├── Dockerfile.dagster        # Container definition for Dagster Web UI
├── Dockerfile.malloy         # Container definition for Malloy Publisher
├── cloudflare_worker.js      # Reverse proxy router script
├── wrangler.json             # Cloudflare Wrangler deployment config
└── README.md                 # Deployment & infrastructure documentation
```

---

## 4. Cost Safeguards & Serverless Configuration

Both GCP Cloud Run services are deployed with strict zero-cost bounds:

* **`--min-instances 0`**: Scales down to 0 when idle ($0 cost when not in use).
* **`--max-instances 1`**: Hard limit preventing runaway scaling or billing spikes.
* **`--concurrency 80`**: Serves up to 80 concurrent HTTP requests per instance.
* **`--cpu-throttling`**: CPU is only billed during active HTTP request processing.
* **`--cpu-boost`**: Allocates 100% CPU during cold container startup probes.
* **`--ingress all`**: Accepts requests proxied through Cloudflare Worker.

---

## 5. Step-by-Step Setup Guide

### Step 1: Google Cloud Platform (GCP) Setup

1. **Create GCP Project**:
   ```bash
   gcloud projects create orca-datawarehouse --name="Orca Data Warehouse"
   gcloud config set project orca-datawarehouse
   ```

2. **Enable Required APIs**:
   ```bash
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com
   ```

3. **Create Service Account**:
   ```bash
   gcloud iam service-accounts create github-actions-deployer \
     --display-name="GitHub Actions Deployer"
   ```

4. **Grant IAM Permissions**:
   ```bash
   gcloud projects add-iam-policy-binding orca-datawarehouse \
     --member="serviceAccount:github-actions-deployer@orca-datawarehouse.iam.gserviceaccount.com" \
     --role="roles/run.admin"

   gcloud projects add-iam-policy-binding orca-datawarehouse \
     --member="serviceAccount:github-actions-deployer@orca-datawarehouse.iam.gserviceaccount.com" \
     --role="roles/artifactregistry.admin"

   gcloud projects add-iam-policy-binding orca-datawarehouse \
     --member="serviceAccount:github-actions-deployer@orca-datawarehouse.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountUser"
   ```

5. **Generate Service Account Key**:
   ```bash
   gcloud iam service-accounts keys create key.json \
     --iam-account=github-actions-deployer@orca-datawarehouse.iam.gserviceaccount.com
   ```

6. **Add GitHub Secret**:
   * Go to GitHub Repository → **Settings** → **Secrets and variables** → **Actions**.
   * Add secret name: **`GCP_SA_KEY`** with the raw JSON contents of `key.json`.

---

### Step 2: Automated Deployment Pipeline (`.github/workflows/deploy_cloud_run.yml`)

The repository includes a GitHub Actions workflow that automatically builds and deploys both services whenever changes are pushed to `main` under `deployment/`, `orchestration/`, or `analytics/`.

To trigger manually:
```bash
gh workflow run "Deploy to GCP Cloud Run"
```

---

### Step 3: Cloudflare Domain & Worker Setup

1. **Add Custom Domain to Cloudflare**:
   * Add `orca-datawarehouse.dev` to your Cloudflare dashboard.

2. **Add Dummy DNS Record**:
   * Go to Cloudflare → **orca-datawarehouse.dev** → **DNS** → **Records**.
   * Add record:
     * **Type**: `AAAA`
     * **Name**: `@`
     * **IPv6 address**: `100::`
     * **Proxy status**: **Proxied** (Orange Cloud ☁️)

3. **Deploy Worker Router**:
   ```bash
   cd deployment
   npx wrangler deploy
   ```

4. **Add Worker Custom Domain**:
   * Go to Cloudflare → **Workers & Pages** → **`orca-router`** → **Domains**.
   * Add Custom Domain: `orca-datawarehouse.dev`.

---

### Step 4: Cloudflare Rate Limiting (WAF Safeguard)

To prevent scraping or DDoS attacks:

1. Go to Cloudflare → **orca-datawarehouse.dev** → **Security** → **WAF** → **Rate limiting rules**.
2. Click **Create rule**:
   * **Rule name**: `General rate limit`
   * **Field**: `Hostname` | **Operator**: `equals` | **Value**: `orca-datawarehouse.dev`
   * **When rate exceeds**: `300` requests per `1 minute`
   * **Action**: `Block` (or `Managed Challenge`)
   * **Duration**: `10 seconds` (or `1 minute`)
3. Click **Deploy**.

---

## 6. Local Testing Commands

To test services locally before building container images:

* **Dagster Web UI**:
  ```bash
  uv run dagster-webserver -h 0.0.0.0 -p 8080 -f orchestration/definitions.py --path-prefix /orchestration --read-only
  ```

* **Malloy Publisher**:
  ```bash
  npx @malloy-publisher/server --config analytics/malloy-config.json --port 8080 --host 0.0.0.0
  ```

---

## 7. Operational & Maintenance Troubleshooting

* **Logs & Observability**:
  * Cloud Run logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=orca-dagster" --limit 50`
  * Worker logs: `cd deployment && npx wrangler tail`
* **Frozen DuckLake Query Verification**:
  * Remote attached database path in `analytics/malloy-config.json`:
    `ATTACH IF NOT EXISTS 'ducklake:https://raw.githubusercontent.com/mathisdrn/orca/main/storage/orca.ducklake' AS orca;`
