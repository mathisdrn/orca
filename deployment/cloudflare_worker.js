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

    // Helper function to proxy requests and rewrite redirect Location headers
    const proxyWithRedirectRewrite = async (targetUrl, backendHost) => {
      const modifiedRequest = new Request(targetUrl, request);
      modifiedRequest.headers.set("Host", backendHost);
      modifiedRequest.headers.set("X-Forwarded-Host", url.host);
      modifiedRequest.headers.set("X-Forwarded-Proto", "https");
      modifiedRequest.headers.set("X-Orca-Proxy-Secret", PROXY_SECRET);

      const response = await fetch(modifiedRequest);
      const location = response.headers.get("Location");
      if (location) {
        const newHeaders = new Headers(response.headers);
        const rewrittenLocation = location.replace(`https://${backendHost}`, url.origin);
        newHeaders.set("Location", rewrittenLocation);
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        });
      }
      return response;
    };

    // 3. Orchestration / Dagster UI -> GCP Cloud Run
    if (pathname.startsWith("/orchestration")) {
      const targetUrl = `${DAGSTER_CLOUD_RUN_URL}${pathname}${url.search}`;
      return proxyWithRedirectRewrite(targetUrl, new URL(DAGSTER_CLOUD_RUN_URL).host);
    }

    // 4. Analytics / Malloy Publisher -> GCP Cloud Run
    if (pathname.startsWith("/analytics")) {
      const targetUrl = `${MALLOY_CLOUD_RUN_URL}${pathname}${url.search}`;
      return proxyWithRedirectRewrite(targetUrl, new URL(MALLOY_CLOUD_RUN_URL).host);
    }

    // 5. Dashboards / Streamlit -> Direct 302 redirect to Streamlit Cloud app
    if (pathname.startsWith("/dashboards")) {
      return Response.redirect(STREAMLIT_APP_URL, 302);
    }

    // Fallback: 404
    return new Response("Route Not Found - Orca Data Warehouse", { status: 404 });
  },
};
