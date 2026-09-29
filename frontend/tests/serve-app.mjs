// Local-only static SPA server for testing the production build.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
const root = resolve('dist/vidhisangh/browser');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
    if (!path.startsWith(root + '/') && path !== root) { res.writeHead(403).end(); return; }
    let body;
    let type = types[extname(path)] ?? 'application/octet-stream';
    try { body = await readFile(path); }
    catch { body = await readFile(resolve(root, 'index.html')); type = 'text/html'; }
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' }).end(body);
  } catch { res.writeHead(500).end(); }
}).listen(4301, '127.0.0.1');
