/**
 * ProxyGuard: Lightweight reverse proxy that blocks direct access to Cloud Run.
 * Only allows requests carrying the valid X-Orca-Proxy-Secret header from Cloudflare Worker.
 */

const http = require('http');

const PROXY_SECRET = process.env.ORCA_PROXY_SECRET || 'orca-cloudflare-secret-987654321';
const LISTEN_PORT = parseInt(process.env.PORT || '8080', 10);
const TARGET_PORT = parseInt(process.env.TARGET_PORT || '8081', 10);

const server = http.createServer((req, res) => {
  const secret = req.headers['x-orca-proxy-secret'];
  if (secret !== PROXY_SECRET) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('403 Forbidden: Direct access denied. Please access via https://orca-datawarehouse.dev\n');
    return;
  }

  const options = {
    hostname: '127.0.0.1',
    port: TARGET_PORT,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${TARGET_PORT}` },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', (err) => {
    console.error('ProxyGuard target error:', err.message);
    res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('502 Bad Gateway: Upstream service starting or unavailable.\n');
  });

  req.pipe(proxyReq, { end: true });
});

server.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`ProxyGuard active on port ${LISTEN_PORT}, forwarding to internal port ${TARGET_PORT}`);
});
