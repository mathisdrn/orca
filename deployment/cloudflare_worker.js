/**
 * Cloudflare Worker Router for orca-datawarehouse.dev
 *
 * Routes:
 *  - /transformation/*  -> GitHub Pages (dbt-docs)
 *  - /orchestration/*   -> GCP Cloud Run (orca-dagster)
 *  - /analytics/*       -> GCP Cloud Run (orca-malloy)
 *  - /dashboards/*      -> Streamlit App (iframe wrapper / redirect)
 *  - /                  -> Redirect to /analytics/
 */

// Replace these URLs with your actual deployed GCP Cloud Run URLs
const DAGSTER_CLOUD_RUN_URL = "https://orca-dagster-120618094679.us-central1.run.app";
const MALLOY_CLOUD_RUN_URL = "https://orca-malloy-120618094679.us-central1.run.app";
const GITHUB_PAGES_URL = "https://mathisdrn.github.io/orca/dbt-docs";
const STREAMLIT_APP_URL = "https://orca-dashboard.streamlit.app";

const PROXY_SECRET = "orca-cloudflare-secret-987654321";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // 0. Redirect www to apex domain
    if (url.hostname.startsWith("www.")) {
      url.hostname = "orca-datawarehouse.dev";
      return Response.redirect(url.toString(), 301);
    }

    // 1. Root path redirect
    if (pathname === "/" || pathname === "") {
      return Response.redirect(`${url.origin}/analytics/`, 302);
    }

    // 2. Transformation / dbt docs -> GitHub Pages
    if (pathname.startsWith("/transformation")) {
      const targetPath = pathname.replace(/^\/transformation/, "");
      const targetUrl = `${GITHUB_PAGES_URL}${targetPath}${url.search}`;
      return fetch(targetUrl, request);
    }

    // 3. Orchestration / Dagster UI -> GCP Cloud Run
    if (pathname.startsWith("/orchestration")) {
      const targetUrl = `${DAGSTER_CLOUD_RUN_URL}${pathname}${url.search}`;
      const modifiedRequest = new Request(targetUrl, request);
      modifiedRequest.headers.set("Host", new URL(DAGSTER_CLOUD_RUN_URL).host);
      modifiedRequest.headers.set("X-Orca-Proxy-Secret", PROXY_SECRET);
      return fetch(modifiedRequest);
    }

    // 4. Analytics / Malloy Publisher -> GCP Cloud Run
    if (pathname.startsWith("/analytics")) {
      const targetUrl = `${MALLOY_CLOUD_RUN_URL}${pathname}${url.search}`;
      const modifiedRequest = new Request(targetUrl, request);
      modifiedRequest.headers.set("Host", new URL(MALLOY_CLOUD_RUN_URL).host);
      modifiedRequest.headers.set("X-Orca-Proxy-Secret", PROXY_SECRET);
      return fetch(modifiedRequest);
    }

    // 5. Dashboards / Streamlit -> Fullscreen Iframe embedding
    if (pathname.startsWith("/dashboards")) {
      const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Orca Dashboards - Streamlit</title>
  <style>
    body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; font-family: system-ui, sans-serif; }
    iframe { width: 100%; height: 100%; border: none; }
  </style>
</head>
<body>
  <iframe src="${STREAMLIT_APP_URL}" allow="camera; microphone; clipboard-read; clipboard-write;"></iframe>
</body>
</html>`;
      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // Fallback: 404
    return new Response("Route Not Found - Orca Data Warehouse", { status: 404 });
  },
};
