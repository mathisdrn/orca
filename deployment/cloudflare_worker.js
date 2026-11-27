/**
 * Cloudflare Worker Router for orca-datawarehouse.dev
 *
 * Routes:
 *  - /, /orchestration, /orchestration/ -> Redirect to /orchestration/asset-groups
 *  - /orchestration/*                    -> GCP Cloud Run (orca-dagster)
 *  - /dashboard/*                        -> Streamlit App (iframe wrapper / redirect)
 */

import COLDSTART_LOADER_HTML from "./coldstart_loader.html";

// Replace these URLs with your actual deployed GCP Cloud Run URLs
const DAGSTER_CLOUD_RUN_URL = "https://orca-dagster-120618094679.us-central1.run.app";
const DEFAULT_ORCHESTRATION_PATH = "/orchestration/asset-groups";
const STREAMLIT_APP_URL = "https://orca-dashboard.streamlit.app/?embed=true";


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

// Regex matching aggressive crawlers and scrapers to preserve serverless quotas
const BLOCKED_BOTS_REGEX = /AhrefsBot|SemrushBot|MJ12bot|DotBot|PetalBot|Bytespider|ClaudeBot|GPTBot|DataForSeoBot|ZoominfoBot|SEOkicks|Baiduspider|BLEXBot|YandexBot/i;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;
    const userAgent = request.headers.get("User-Agent") || "";

    // 0. Robots.txt route to prevent search engines and crawlers from indexing serverless backends
    if (pathname === "/robots.txt") {
      return new Response(
        "User-agent: *\nDisallow: /orchestration/\nAllow: /$\nAllow: /dashboard/\n",
        {
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "public, max-age=86400",
          },
        }
      );
    }

    // Block aggressive commercial scrapers & SEO crawlers from waking up Cloud Run
    if (BLOCKED_BOTS_REGEX.test(userAgent)) {
      return new Response("Forbidden: Bot crawling is restricted to protect serverless quotas.", {
        status: 403,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    // 0. Redirect www to apex domain
    if (url.hostname.startsWith("www.")) {
      url.hostname = "orca-datawarehouse.dev";
      return Response.redirect(url.toString(), 301);
    }

    // 1. Root & bare orchestration path redirect
    if (
      pathname === "/" ||
      pathname === "" ||
      pathname === "/orchestration" ||
      pathname === "/orchestration/"
    ) {
      return Response.redirect(`${url.origin}${DEFAULT_ORCHESTRATION_PATH}`, 302);
    }

    // Inject a CSP-nonced script that dynamically expands all Dagster asset groups once per tab session
    const injectAutoExpandScript = (response) => {
      const contentType = response.headers.get("Content-Type") || "";
      if (!response.ok || !contentType.includes("text/html")) {
        return response;
      }

      const csp = response.headers.get("Content-Security-Policy") || "";
      const nonceMatch = csp.match(/'nonce-([^']+)'/);
      const nonceAttr = nonceMatch ? ` nonce="${nonceMatch[1]}"` : "";

      const script = `<script${nonceAttr}>(function(){try{var STORAGE_KEY="asset-graph-open-graph-nodes-global-__GLOBAL__",SESSION_KEY="orca_asset_groups_expanded";var sp=new URLSearchParams(location.search),force=sp.has("expanded")&&!sp.get("expanded");if(force){sp.delete("expanded");var qs=sp.toString();history.replaceState(null,"",location.pathname+(qs?"?"+qs:"")+location.hash);}if(!force&&sessionStorage.getItem(SESSION_KEY))return;fetch("/orchestration/graphql",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:"{ assetNodes { groupName repository { name location { name } } } }"})}).then(function(r){return r.ok?r.json():null;}).then(function(res){var nodes=res&&res.data&&res.data.assetNodes;if(!Array.isArray(nodes))return;var perLoc=false;try{var flags=JSON.parse(localStorage.getItem("DAGSTER_FLAGS")||"{}");perLoc=Boolean(flags&&flags.flagAssetGraphGroupsPerCodeLocation);}catch(e){}var seen={},groups=[];for(var i=0;i<nodes.length;i++){var n=nodes[i];if(!n||!n.groupName)continue;var gid=perLoc&&n.repository&&n.repository.location?n.repository.name+"@"+n.repository.location.name+":"+n.groupName:"global@global:"+n.groupName;if(!seen[gid]){seen[gid]=true;groups.push(gid);}}if(groups.length>0){localStorage.setItem(STORAGE_KEY,JSON.stringify({expanded:groups.join(",")}));sessionStorage.setItem(SESSION_KEY,"1");document.dispatchEvent(new CustomEvent("",{detail:STORAGE_KEY}));}}).catch(function(){});}catch(e){}})();</script>`;

      return new HTMLRewriter()
        .on("head", {
          element(el) {
            el.append(script, { html: true });
          },
        })
        .transform(response);
    };

    // Helper function to proxy requests and rewrite redirect Location headers
    const proxyWithRedirectRewrite = async (targetUrl, backendHost, requireAuth = false, timeoutMs = null) => {
      const modifiedRequest = new Request(targetUrl, request);
      modifiedRequest.headers.set("Host", backendHost);
      modifiedRequest.headers.set("X-Forwarded-Host", url.host);
      modifiedRequest.headers.set("X-Forwarded-Proto", "https");

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

    // 2. Orchestration / Dagster UI -> GCP Cloud Run (Protected by OIDC)
    if (pathname === "/orchestration" || pathname.startsWith("/orchestration/")) {
      const targetUrl = `${DAGSTER_CLOUD_RUN_URL}${pathname}${url.search}`;

      // Edge-cache immutable static assets (JS chunks, CSS, fonts) to eliminate Cloud Run invocations & egress bandwidth
      if (pathname.startsWith("/orchestration/_next/static/") || pathname.startsWith("/orchestration/static/")) {
        const cache = caches.default;
        const cacheKey = new Request(url.toString(), request);
        let cachedResponse = await cache.match(cacheKey);
        if (cachedResponse) {
          return cachedResponse;
        }

        const response = await proxyWithRedirectRewrite(targetUrl, new URL(DAGSTER_CLOUD_RUN_URL).host, true);
        if (response.ok) {
          const responseToCache = new Response(response.body, response);
          responseToCache.headers.set("Cache-Control", "public, max-age=2592000, immutable");
          ctx.waitUntil(cache.put(cacheKey, responseToCache.clone()));
          return responseToCache;
        }
        return response;
      }

      // On cold start, Cloud Run may return 503. Detect and serve loading page instead.
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
          return injectAutoExpandScript(response);
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

    // 3. Dashboard / Streamlit -> Seamless Fullscreen Iframe
    if (pathname === "/dashboard" || pathname.startsWith("/dashboard/")) {
      const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Orca Dashboard - Streamlit</title>
  <style>
    body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; font-family: system-ui, sans-serif; background-color: #ffffff; }
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
