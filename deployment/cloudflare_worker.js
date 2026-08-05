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
const STREAMLIT_APP_URL = "https://orca-dashboard.streamlit.app/?embed=true";

const PROXY_SECRET = "orca-cloudflare-secret-987654321";

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
    const proxyWithRedirectRewrite = async (targetUrl, backendHost, requireAuth = false) => {
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

      const response = await fetch(modifiedRequest);
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
    };

    // 3. Orchestration / Dagster UI -> GCP Cloud Run (Protected by OIDC)
    if (pathname.startsWith("/orchestration")) {
      const targetUrl = `${DAGSTER_CLOUD_RUN_URL}${pathname}${url.search}`;
      return proxyWithRedirectRewrite(targetUrl, new URL(DAGSTER_CLOUD_RUN_URL).host, true);
    }

    // 4. Analytics / Malloy Publisher -> GCP Cloud Run
    if (pathname.startsWith("/analytics")) {
      const targetUrl = `${MALLOY_CLOUD_RUN_URL}${pathname}${url.search}`;
      return proxyWithRedirectRewrite(targetUrl, new URL(MALLOY_CLOUD_RUN_URL).host);
    }

    // 5. Dashboards / Streamlit -> Seamless Fullscreen Iframe
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
