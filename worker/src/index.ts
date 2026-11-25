export interface Env {
  PHASE2_LAB_KV: KVNamespace;
  RATE_LIMIT_KV: KVNamespace;
  COMPUTE_BASE_URL?: string;
  COMPUTE_AUTH_TOKEN?: string;
  ALLOWED_ORIGIN: string;
  MAX_RUNS_PER_IP_PER_HOUR: string;
  ASSETS?: Fetcher;
}

type LabId = 'report' | 'vehicle' | 'pod' | 'solver' | 'deals';
const VALID_LABS = new Set<LabId>(['report', 'vehicle', 'pod', 'solver', 'deals']);

function corsHeaders(env: Env): Record<string, string> {
  return {
    'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  };
}

function jsonResp(data: unknown, status: number, env: Env): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(env) },
  });
}

async function sha16(canonical: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16);
}

function nearest(val: number, choices: readonly number[]): number {
  return choices.reduce((best, cur) => (Math.abs(cur - val) < Math.abs(best - val) ? cur : best), choices[0]);
}

async function normalizeAndKey(lab: LabId, raw: Record<string, unknown>) {
  if (lab === 'report') {
    const case_type = String(raw.case_type ?? 'step').toLowerCase() === 'pipe' ? 'pipe' : 'step';
    const re_or_u =
      case_type === 'step'
        ? nearest(Number(raw.re_or_u ?? 37500), [400, 37500])
        : nearest(Number(raw.re_or_u ?? 2.0), [0.03, 2.0, 4.0]);
    return { params: { case_type, re_or_u }, key: await sha16(`p2|report|${case_type}|${re_or_u.toFixed(2)}`) };
  }
  if (lab === 'vehicle') {
    const annual_km = Math.round(Math.min(Math.max(Number(raw.annual_km ?? 20000), 5000), 80000));
    const elec_price = Number(Math.min(Math.max(Number(raw.elec_price ?? 0.3), 0.1), 1.0).toFixed(2));
    return {
      params: { annual_km, elec_price },
      key: await sha16(`p2|vehicle|km=${annual_km.toFixed(0)}|p=${elec_price.toFixed(2)}`),
    };
  }
  if (lab === 'pod') {
    const shape = String(raw.shape ?? 'cylinder').toLowerCase() === 'eureka' ? 'eureka' : 'cylinder';
    const re = Math.round(Math.min(Math.max(Number(raw.re ?? 150), 80), 220) / 10) * 10;
    return { params: { shape, re }, key: await sha16(`p2|pod|${shape}|${re.toFixed(0)}`) };
  }
  if (lab === 'solver') {
    const re = nearest(Number(raw.re ?? 400), [100, 400, 1000]);
    const grid_n = nearest(Number(raw.grid_n ?? 65), [49, 65, 81]);
    return { params: { re, grid_n }, key: await sha16(`p2|solver|re=${re}|n=${grid_n}`) };
  }
  const st = String(raw.store ?? 'ALL');
  const store = st === 'Coles' || st === 'Woolworths' ? st : 'ALL';
  const min_discount_pct = nearest(Number(raw.min_discount_pct ?? 0), [0, 10, 20]);
  return {
    params: { store, min_discount_pct },
    key: await sha16(`p2|deals|${store}|${min_discount_pct.toFixed(0)}`),
  };
}

function buildResultUrls(lab: LabId, caseKey: string) {
  return {
    json: `/api/results/${lab}/${caseKey}/payload.json`,
    png: `/api/results/${lab}/${caseKey}/report.png`,
    csv: `/api/results/${lab}/${caseKey}/data.csv`,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    if (!path.startsWith('/api/')) {
      if (env.ASSETS) return env.ASSETS.fetch(request);
      return new Response('Not Found', { status: 404 });
    }

    if (path === '/api/health') {
      return jsonResp(
        {
          status: 'ok',
          labs: ['report', 'vehicle', 'pod', 'solver', 'deals'],
          compute_configured: Boolean(env.COMPUTE_BASE_URL),
        },
        200,
        env
      );
    }

    const casesMatch = path.match(/^\/api\/cases\/(report|vehicle|pod|solver|deals)$/);
    if (casesMatch && request.method === 'GET') {
      const lab = casesMatch[1] as LabId;
      const raw = await env.PHASE2_LAB_KV.get(`index:${lab}`);
      return jsonResp({ lab, cases: raw ? JSON.parse(raw) : [] }, 200, env);
    }

    const resMatch = path.match(/^\/api\/results\/(report|vehicle|pod|solver|deals)\/([a-f0-9]{16})\/(payload\.json|report\.png|data\.csv)$/);
    if (resMatch && (request.method === 'GET' || request.method === 'HEAD')) {
      const [, lab, caseKey, fname] = resMatch;
      const raw = await env.PHASE2_LAB_KV.get(`case:${lab}:${caseKey}:payload.json`);
      if (!raw) return jsonResp({ error: 'Not found in KV' }, 404, env);
      const payload = JSON.parse(raw) as { image_b64: string; csv_content: string };

      if (fname === 'payload.json') {
        return new Response(request.method === 'HEAD' ? null : raw, {
          status: 200,
          headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=31536000, immutable', ...corsHeaders(env) },
        });
      }
      if (fname === 'data.csv') {
        return new Response(request.method === 'HEAD' ? null : '\uFEFF' + (payload.csv_content || ''), {
          status: 200,
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': `attachment; filename="phase2_${lab}_${caseKey}.csv"`,
            ...corsHeaders(env),
          },
        });
      }
      const bin = Uint8Array.from(atob(payload.image_b64), (c) => c.charCodeAt(0));
      return new Response(request.method === 'HEAD' ? null : bin.buffer, {
        status: 200,
        headers: {
          'Content-Type': 'image/png',
          'Cache-Control': 'public, max-age=31536000, immutable',
          ...corsHeaders(env),
        },
      });
    }

    const runMatch = path.match(/^\/api\/run\/(report|vehicle|pod|solver|deals)$/);
    if (runMatch && request.method === 'POST') {
      const lab = runMatch[1] as LabId;
      if (!VALID_LABS.has(lab)) return jsonResp({ error: 'Invalid lab' }, 400, env);

      let body: Record<string, unknown> = {};
      try {
        body = (await request.json()) as Record<string, unknown>;
      } catch {
        return jsonResp({ error: 'Invalid JSON' }, 400, env);
      }

      const { params, key: caseKey } = await normalizeAndKey(lab, body);
      const force = Boolean(body.force);

      if (!force) {
        const cachedRaw = await env.PHASE2_LAB_KV.get(`case:${lab}:${caseKey}:payload.json`);
        if (cachedRaw) {
          const parsed = JSON.parse(cachedRaw);
          return jsonResp(
            {
              status: 'ok',
              cached: true,
              backend: 'cloudflare-kv-cache',
              lab,
              case_key: caseKey,
              result: parsed,
              urls: buildResultUrls(lab, caseKey),
            },
            200,
            env
          );
        }
      }

      if (!env.COMPUTE_BASE_URL) return jsonResp({ error: 'COMPUTE_BASE_URL missing' }, 503, env);

      const ip = request.headers.get('CF-Connecting-IP') || 'anon';
      const hourBucket = Math.floor(Date.now() / 3600000);
      const rlKey = `rl:phase2:${ip}:${hourBucket}`;
      const limit = Math.max(1, parseInt(env.MAX_RUNS_PER_IP_PER_HOUR || '30', 10));
      const used = parseInt((await env.RATE_LIMIT_KV.get(rlKey)) || '0', 10);
      if (used >= limit) return jsonResp({ error: `Hourly quota reached (${limit}/hr)` }, 429, env);

      const base = env.COMPUTE_BASE_URL.replace(/\/$/, '');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (env.COMPUTE_AUTH_TOKEN) headers['Authorization'] = `Bearer ${env.COMPUTE_AUTH_TOKEN}`;

      const modalRes = await fetch(`${base}/run/${lab}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(params),
      });
      if (!modalRes.ok) {
        const errText = await modalRes.text();
        return jsonResp({ error: `Cloud Python (${lab}) failed (${modalRes.status}): ${errText.slice(0, 600)}` }, 502, env);
      }

      const payload = (await modalRes.json()) as {
        case_key: string;
        lab: string;
        params: Record<string, unknown>;
        kpis: Record<string, unknown>;
        timing_sec: number;
      };

      const summary = {
        case_key: caseKey,
        lab,
        params: payload.params,
        kpis: payload.kpis,
        timing_sec: payload.timing_sec,
      };

      await env.PHASE2_LAB_KV.put(`case:${lab}:${caseKey}:payload.json`, JSON.stringify(payload));
      const idxRaw = await env.PHASE2_LAB_KV.get(`index:${lab}`);
      const idxList: Array<{ case_key: string }> = idxRaw ? JSON.parse(idxRaw) : [];
      const updated = [summary, ...idxList.filter((x) => x.case_key !== caseKey)].slice(0, 20);
      await env.PHASE2_LAB_KV.put(`index:${lab}`, JSON.stringify(updated));
      await env.RATE_LIMIT_KV.put(rlKey, String(used + 1), { expirationTtl: 3900 });

      return jsonResp(
        {
          status: 'ok',
          cached: false,
          backend: 'modal-python-openfoam',
          lab,
          case_key: caseKey,
          result: payload,
          urls: buildResultUrls(lab, caseKey),
        },
        200,
        env
      );
    }

    return jsonResp({ error: 'Not found' }, 404, env);
  },
};
