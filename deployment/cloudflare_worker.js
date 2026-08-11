/**
 * Cloudflare Worker Router for orca-datawarehouse.dev
 *
 * Routes:
 *  - /transformation/*  -> GitHub Pages (dbt-docs)
 *  - /orchestration/*   -> GCP Cloud Run (orca-dagster)
 *  - /dashboards/*      -> Streamlit App (iframe wrapper / redirect)
 *  - /                  -> Redirect to /orchestration/
 */

// Replace these URLs with your actual deployed GCP Cloud Run URLs
const DAGSTER_CLOUD_RUN_URL = "https://orca-dagster-120618094679.us-central1.run.app";
const GITHUB_PAGES_URL = "https://mathisdrn.github.io/orca/dbt-docs";
const STREAMLIT_APP_URL = "https://orca-dashboard.streamlit.app/?embed=true";

const PROXY_SECRET = "orca-cloudflare-secret-987654321";

const COLDSTART_LOADER_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Orca Data Warehouse – Starting Instance</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: #0f172a;
      color: #f8fafc;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .card {
      background-color: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 40px 32px;
      width: 100%;
      max-width: 440px;
      text-align: center;
    }
    .logo-container { margin-bottom: 20px; display: flex; justify-content: center; }
    .logo {
      width: 48px; height: 48px;
      background-color: #0284c7;
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
    }
    .logo svg { width: 28px; height: 28px; fill: none; stroke: #ffffff; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .status-badge {
      display: inline-flex; align-items: center; gap: 8px;
      background-color: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.2);
      color: #38bdf8; padding: 4px 12px; border-radius: 9999px;
      font-size: 0.8rem; font-weight: 500; margin-bottom: 20px;
    }
    .pulse-dot { width: 6px; height: 6px; background-color: #38bdf8; border-radius: 50%; animation: pulse 1.5s ease-in-out infinite; }
    h1 { font-size: 1.35rem; font-weight: 600; color: #f8fafc; margin-bottom: 12px; }
    p { color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 28px; }
    .spinner-wrapper { position: relative; width: 40px; height: 40px; margin: 0 auto 24px auto; }
    .spinner {
      width: 100%; height: 100%;
      border: 3px solid #334155;
      border-top: 3px solid #38bdf8;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    .timer { font-size: 0.85rem; color: #64748b; font-variant-numeric: tabular-nums; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo-container">
      <div class="logo">
        <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
      </div>
    </div>
    <div class="status-badge">
      <div class="pulse-dot"></div>
      <span>GCP Serverless Instance</span>
    </div>
    <h1>Starting Dagster UI...</h1>
    <p>The serverless instance is spinning up to save resources. Spin-up usually takes about 30 seconds. You will be automatically redirected as soon as the server is ready.</p>
    <div class="spinner-wrapper"><div class="spinner"></div></div>
    <div class="timer" id="timer">Time elapsed: 0s</div>
  </div>
  <script>
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const TARGET_URL = window.location.origin + '/orchestration/';
    const POLL_INTERVAL_MS = 2000;
    let secondsElapsed = 0;
    const timerElem = document.getElementById('timer');
    setInterval(() => { secondsElapsed++; timerElem.textContent = 'Time elapsed: ' + secondsElapsed + 's'; }, 1000);
    async function checkAvailability() {
      if (isLocalhost) return;
      try {
        const response = await fetch(TARGET_URL, { method: 'HEAD', headers: { 'Accept': 'application/json' } });
        if (response.ok) { window.location.href = TARGET_URL; }
      } catch (err) { /* still cold, keep polling */ }
    }
    if (!isLocalhost) {
      setInterval(checkAvailability, POLL_INTERVAL_MS);
      checkAvailability();
    }
  <\/script>
</body>
</html>`;


// Cache OIDC token per target audience in worker instance memory
const tokenCache = {};

function base64url(source) {
  let encoded = btoa(source);
  return encoded.replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function arrayBufferToBase64Url(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return base64url(binary);
}

function pemToBinary(pem) {
  const pemContents = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const binaryDerString = atob(pemContents);
  const binaryDer = new Uint8Array(binaryDerString.length);
  for (let i = 0; i < binaryDerString.length; i++) {
    binaryDer[i] = binaryDerString.charCodeAt(i);
  }
  return binaryDer.buffer;
}

async function getGoogleOidcToken(targetAudience, env) {
  const now = Math.floor(Date.now() / 1000);
  const cached = tokenCache[targetAudience];
  if (cached && cached.expiresAt > now + 300) {
    return cached.token;
  }

  const saEmail = env.GCP_SA_EMAIL;
  const privateKeyPem = env.GCP_SA_PRIVATE_KEY;

  if (!saEmail || !privateKeyPem) {
    console.warn("GCP Service Account credentials missing in worker env.");
    return null;
  }

  try {
    const binaryKey = pemToBinary(privateKeyPem);
    const cryptoKey = await crypto.subtle.importKey(
      "pkcs8",
      binaryKey,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["sign"]
    );

    const header = { alg: "RS256", typ: "JWT" };
    const payload = {
      iss: saEmail,
      sub: saEmail,
      aud: "https://oauth2.googleapis.com/token",
      target_audience: targetAudience,
      iat: now,
      exp: now + 3600,
    };

    const encodedHeader = base64url(JSON.stringify(header));
    const encodedPayload = base64url(JSON.stringify(payload));
    const dataToSign = `${encodedHeader}.${encodedPayload}`;

    const signature = await crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      cryptoKey,
      new TextEncoder().encode(dataToSign)
    );

    const jwt = `${dataToSign}.${arrayBufferToBase64Url(signature)}`;

    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
        assertion: jwt,
      }),
    });

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      console.error("Failed to fetch Google OIDC token:", tokenResponse.status, errorText);
      return null;
    }

    const tokenData = await tokenResponse.json();
    tokenCache[targetAudience] = {
      token: tokenData.id_token,
      expiresAt: now + 3500,
    };
    return tokenData.id_token;
  } catch (err) {
    console.error("Error generating OIDC token:", err);
    return null;
  }
}

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
      return Response.redirect(`${url.origin}/orchestration/`, 302);
    }

    // 2. Transformation / dbt docs -> GitHub Pages
    if (pathname.startsWith("/transformation")) {
      const targetPath = pathname.replace(/^\/transformation/, "");
      const targetUrl = `${GITHUB_PAGES_URL}${targetPath}${url.search}`;
      return fetch(targetUrl, request);
    }

    // Helper function to proxy requests and rewrite redirect Location headers
    const proxyWithRedirectRewrite = async (targetUrl, backendHost, requireAuth = false, timeoutMs = null) => {
      const modifiedRequest = new Request(targetUrl, request);
      modifiedRequest.headers.set("Host", backendHost);
      modifiedRequest.headers.set("X-Forwarded-Host", url.host);
      modifiedRequest.headers.set("X-Forwarded-Proto", "https");
      modifiedRequest.headers.set("X-Orca-Proxy-Secret", PROXY_SECRET);

      if (requireAuth) {
        const idToken = await getGoogleOidcToken(new URL(targetUrl).origin, env);
        if (idToken) {
          modifiedRequest.headers.set("Authorization", `Bearer ${idToken}`);
        }
      }

      let timeoutId;
      const options = {};
      if (timeoutMs) {
        const controller = new AbortController();
        timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        options.signal = controller.signal;
      }

      try {
        const response = await fetch(modifiedRequest, options);
        if (timeoutId) clearTimeout(timeoutId);

        const location = response.headers.get("Location");
        if (location) {
          const newHeaders = new Headers(response.headers);
          const rewrittenLocation = location.replace(new RegExp(`https?://${backendHost}`, 'g'), url.origin);
          newHeaders.set("Location", rewrittenLocation);
          return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: newHeaders,
          });
        }
        return response;
      } catch (err) {
        if (timeoutId) clearTimeout(timeoutId);
        throw err;
      }
    };

    // 3. Orchestration / Dagster UI -> GCP Cloud Run (Protected by OIDC)
    if (pathname.startsWith("/orchestration")) {
      // On cold start, Cloud Run may return 503. Detect and serve loading page instead.
      const targetUrl = `${DAGSTER_CLOUD_RUN_URL}${pathname}${url.search}`;

      // Only show the loader for browser navigation (not for API/asset sub-requests)
      const acceptHeader = request.headers.get("Accept") || "";
      const isBrowserNav = acceptHeader.includes("text/html");

      if (isBrowserNav) {
        try {
          // Serve loading page if the cold backend takes more than 2 seconds to respond
          const response = await proxyWithRedirectRewrite(targetUrl, new URL(DAGSTER_CLOUD_RUN_URL).host, true, 2000);
          // Cloud Run returns 503 during cold start / scale-from-zero
          if (response.status === 503 || response.status === 502 || response.status === 504) {
            return new Response(COLDSTART_LOADER_HTML, {
              status: 503,
              headers: { "Content-Type": "text/html; charset=utf-8" },
            });
          }
          return response;
        } catch (err) {
          // Network error or AbortError (timeout) => instance is cold, show loader
          return new Response(COLDSTART_LOADER_HTML, {
            status: 503,
            headers: { "Content-Type": "text/html; charset=utf-8" },
          });
        }
      }

      return proxyWithRedirectRewrite(targetUrl, new URL(DAGSTER_CLOUD_RUN_URL).host, true);
    }

    // 4. Dashboards / Streamlit -> Seamless Fullscreen Iframe
    if (pathname.startsWith("/dashboards")) {
      const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Orca Dashboards - Streamlit</title>
  <style>
    body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; font-family: system-ui, sans-serif; background-color: #0e1117; }
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
