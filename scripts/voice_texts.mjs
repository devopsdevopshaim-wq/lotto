// Collect the exact texts the site reads aloud, so they can be recorded with a natural voice.
// Serves the repo locally, opens lotto.html?voicegen in headless Chrome and saves voice/texts.json.
// Needs playwright-core (npm i --no-save playwright-core) and a Chrome/Chromium binary (CHROME env or /usr/bin/google-chrome).
import http from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const TYPES = { '.html': 'text/html; charset=utf-8', '.csv': 'text/csv', '.json': 'application/json', '.js': 'text/javascript', '.mp3': 'audio/mpeg' };

const server = http.createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^([/\\])+/, '');
  if (path.startsWith('..')) { res.writeHead(403).end(); return; }
  try {
    const body = await readFile(join(ROOT, path || 'index.html'));
    res.writeHead(200, { 'Content-Type': TYPES[extname(path)] || 'application/octet-stream' }).end(body);
  } catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.goto(`http://127.0.0.1:${port}/lotto.html?voicegen`);
  await page.waitForSelector('#voicegen', { state: 'attached', timeout: 120000 });
  const texts = JSON.parse(await page.$eval('#voicegen', el => el.textContent));
  await mkdir(join(ROOT, 'voice'), { recursive: true });
  await writeFile(join(ROOT, 'voice', 'texts.json'), JSON.stringify(texts, null, 1) + '\n');
  const chars = Object.values(texts).reduce((a, t) => a + t.text.length, 0);
  console.log(`voice/texts.json: ${Object.keys(texts).length} texts, ${chars} characters`);
} finally {
  await browser.close();
  server.close();
}
