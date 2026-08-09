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
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Orca Data Warehouse – Démarrage de l'instance</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at 50% 30%, #1e293b 0%, #0f172a 100%);
      color: #f8fafc;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    .card {
      background: rgba(30, 41, 59, 0.7);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      padding: 48px;
      width: 90%;
      max-width: 480px;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
      animation: fadeIn 0.8s ease-out;
    }
    .logo-container { margin-bottom: 24px; display: flex; justify-content: center; }
    .logo {
      width: 64px; height: 64px;
      background: linear-gradient(135deg, #0ea5e9, #6366f1);
      border-radius: 16px;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 0 24px rgba(14, 165, 233, 0.4);
    }
    .logo svg { width: 36px; height: 36px; fill: none; stroke: white; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    h1 {
      font-size: 1.5rem; font-weight: 600; margin-bottom: 12px;
      background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    p { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; margin-bottom: 32px; }
    .spinner-wrapper { position: relative; width: 64px; height: 64px; margin: 0 auto 32px auto; }
    .spinner {
      width: 100%; height: 100%;
      border: 4px solid rgba(14, 165, 233, 0.15);
      border-top: 4px solid #0ea5e9;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    .timer { font-size: 0.85rem; color: #64748b; font-variant-numeric: tabular-nums; }
    .status-badge {
      display: inline-flex; align-items: center; gap: 8px;
      background: rgba(14, 165, 233, 0.1);
      border: 1px solid rgba(14, 165, 233, 0.2);
      color: #38bdf8; padding: 6px 14px; border-radius: 9999px;
      font-size: 0.85rem; font-weight: 500; margin-bottom: 16px;
    }
    .pulse-dot { width: 8px; height: 8px; background-color: #38bdf8; border-radius: 50%; animation: pulse 1.5s ease-in-out infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.8); } }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
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
      <span>Instance Serverless GCP</span>
    </div>
    <h1>Démarrage de Dagster UI...</h1>
    <p>L'instance serverless s'éveille pour économiser vos ressources. Redirection automatique dès que le serveur est prêt.</p>
    <div class="spinner-wrapper"><div class="spinner"></div></div>
    <div class="timer" id="timer">Temps écoulé : 0s</div>
  </div>
  <script>
    const TARGET_URL = window.location.origin + '/orchestration/';
    const POLL_INTERVAL_MS = 2000;
    let secondsElapsed = 0;
    const timerElem = document.getElementById('timer');
    setInterval(() => { secondsElapsed++; timerElem.textContent = 'Temps écoulé : ' + secondsElapsed + 's'; }, 1000);
    async function checkAvailability() {
      try {
        const response = await fetch(TARGET_URL, { method: 'HEAD' });
        if (response.ok) { window.location.href = TARGET_URL; }
      } catch (err) { /* still cold, keep polling */ }
    }
    setInterval(checkAvailability, POLL_INTERVAL_MS);
    checkAvailability();
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
              headers: { "Content-Type": "text/html; charset=utf-8" },
            });
          }
          return response;
        } catch (err) {
          // Network error or AbortError (timeout) => instance is cold, show loader
          return new Response(COLDSTART_LOADER_HTML, {
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
