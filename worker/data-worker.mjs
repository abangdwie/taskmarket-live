// taskmarket-live data worker — server-side fetch + cache for the dashboard.
// Fetches ONLY public Taskmarket API endpoints (no key), combines both chains,
// caches 10 minutes in the edge cache. No wallet, no tracking, no personal data.
const API = 'https://api.taskmarket.dev';
const CHAINS = [4217, 8453];
const CACHE_TTL = 600; // seconds; task requires cache >= 60s, refresh >= hourly

async function getJSON(url) {
  const r = await fetch(url, { headers: { accept: 'application/json' } });
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json();
}

async function chainData(chainId) {
  const [stats, breakdowns, series90, heatMode, heatHow, feed] = await Promise.all([
    getJSON(`${API}/api/market/stats?chainId=${chainId}`),
    getJSON(`${API}/api/stats/breakdowns?chainId=${chainId}`),
    getJSON(`${API}/api/stats/platform-time-series?chainId=${chainId}&range=90d&bucket=day`),
    getJSON(`${API}/api/stats/activity-heatmap?chainId=${chainId}&range=30d&dimension=mode`),
    getJSON(`${API}/api/stats/activity-heatmap?chainId=${chainId}&range=7d&dimension=hourOfWeek`),
    getJSON(`${API}/api/stats/activity-feed?chainId=${chainId}&limit=50`),
  ]);

  // Distinct posters of the last 7 days: paginate newest tasks until older than 7d.
  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const posters = new Map(); // requester -> {count, displayName}
  let cursor = null, pages = 0, done = false, newestSeen = 0;
  while (!done && pages < 8) {
    const u = `${API}/api/tasks?chainId=${chainId}&sort=newest&limit=100` + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
    const page = await getJSON(u);
    pages++;
    for (const t of page.tasks || []) {
      newestSeen++;
      if (new Date(t.createdAt).getTime() < weekAgo) { done = true; break; }
      const key = t.requester || 'unknown';
      const cur = posters.get(key) || { count: 0, displayName: t.requesterDisplayName || null };
      cur.count++;
      posters.set(key, cur);
    }
    cursor = page.nextCursor || page.cursor || null;
    if (!cursor) break;
  }
  const topPosters = [...posters.entries()]
    .map(([address, v]) => ({ address, count: v.count, displayName: v.displayName }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return {
    chainId, stats, breakdowns, series90, heatMode, heatHow,
    feed: feed.items || [],
    postersWeek: {
      distinct: posters.size,
      tasksCounted: newestSeen,
      top: topPosters,
      top5Share: topPosters.slice(0, 5).reduce((s, p) => s + p.count, 0) / Math.max(1, newestSeen),
    },
  };
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const cors = {
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET, OPTIONS',
      'access-control-max-age': '86400',
    };
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (url.pathname === '/api/health') {
      return new Response(JSON.stringify({ ok: true, at: new Date().toISOString() }), { headers: { 'content-type': 'application/json', ...cors } });
    }
    if (url.pathname !== '/api/data') {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404, headers: { 'content-type': 'application/json', ...cors } });
    }

    const cache = caches.default;
    const cacheKey = new Request(url.toString(), request);
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    try {
      const started = Date.now();
      const [tempo, base] = await Promise.all([chainData(4217), chainData(8453)]);
      const payload = {
        dataAsOf: new Date().toISOString(),
        fetchMs: Date.now() - started,
        cacheSeconds: CACHE_TTL,
        sources: [
          '/api/market/stats', '/api/stats/breakdowns',
          '/api/stats/platform-time-series', '/api/stats/activity-heatmap',
          '/api/stats/activity-feed', '/api/tasks',
        ],
        chains: { tempo, base },
      };
      const res = new Response(JSON.stringify(payload), {
        headers: {
          'content-type': 'application/json',
          'cache-control': `public, max-age=${CACHE_TTL}`,
          ...cors,
        },
      });
      await cache.put(cacheKey, res.clone());
      return res;
    } catch (err) {
      return new Response(JSON.stringify({ error: String(err && err.message || err) }), {
        status: 502, headers: { 'content-type': 'application/json', ...cors },
      });
    }
  },
};
