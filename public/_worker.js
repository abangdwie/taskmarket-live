// taskmarket-live — Cloudflare Pages `_worker.js` (advanced mode).
// Serves /api/data (server-side fetch of the public Taskmarket API for both
// chains, cached 600s at the edge) and falls through to the static site for
// everything else. No key, no login, no wallet, no tracking.
const API = 'https://api.taskmarket.dev';
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
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/api/data' && url.pathname !== '/api/health') {
      return env.ASSETS.fetch(request);
    }
    if (url.pathname === '/api/health') {
      return new Response(JSON.stringify({ ok: true, at: new Date().toISOString() }), {
        headers: { 'content-type': 'application/json' },
      });
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
        },
      });
      await cache.put(cacheKey, res.clone());
      return res;
    } catch (err) {
      return new Response(JSON.stringify({ error: String((err && err.message) || err) }), {
        status: 502, headers: { 'content-type': 'application/json' },
      });
    }
  },
};
