import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  Check,
  Code2,
  Copy,
  Database,
  Download,
  FileSpreadsheet,
  Flame,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Sliders,
  Sparkles,
  Table2,
  Timer,
} from 'lucide-react';
import { detectInitialLang, TRANSLATIONS, type Lang } from './i18n';
import type { LabId, LabResponse, LabSummary } from './types';

function detectInitialLab(): LabId {
  try {
    const q = new URLSearchParams(window.location.search).get('lab');
    if (q === 'report' || q === 'vehicle' || q === 'pod' || q === 'solver' || q === 'deals') return q;
  } catch { /* ignore */ }
  return 'report';
}

const DEFAULT_PARAMS: Record<LabId, Record<string, any>> = {
  report: { case_type: 'step', re_or_u: 37500 },
  vehicle: { annual_km: 20000, elec_price: 0.3 },
  pod: { shape: 'cylinder', re: 150 },
  solver: { re: 400, grid_n: 65 },
  deals: { store: 'ALL', min_discount_pct: 0 },
};

export const App: React.FC = () => {
  const [lang, setLang] = useState<Lang>(detectInitialLang);
  const [lab, setLab] = useState<LabId>(detectInitialLab);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [paramsMap, setParamsMap] = useState<Record<LabId, Record<string, any>>>(DEFAULT_PARAMS);
  const [results, setResults] = useState<Partial<Record<LabId, LabResponse>>>({});
  const [cachedMap, setCachedMap] = useState<Record<LabId, LabSummary[]>>({
    report: [],
    vehicle: [],
    pod: [],
    solver: [],
    deals: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const t = TRANSLATIONS[lang];
  const curParams = paramsMap[lab];
  const curRes = results[lab] ?? null;
  const curCached = cachedMap[lab] ?? [];

  useEffect(() => {
    document.title = t.pageTitle;
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    try { localStorage.setItem('p2_lang', lang); } catch { /* ignore */ }
  }, [lang, t.pageTitle]);

  const loadCached = useCallback(async (target: LabId) => {
    try {
      const res = await fetch(`/api/cases/${target}`);
      if (!res.ok) return;
      const d = (await res.json()) as { cases?: LabSummary[] };
      const list = d.cases ?? [];
      setCachedMap((prev) => ({ ...prev, [target]: list }));
      if (list.length > 0 && !results[target]) {
        const first = list[0];
        const pr = await fetch(`/api/results/${target}/${first.case_key}/payload.json`);
        if (pr.ok) {
          const payload = await pr.json();
          setResults((prev) => ({
            ...prev,
            [target]: {
              status: 'ok',
              cached: true,
              backend: 'cloudflare-kv-cache',
              lab: target,
              case_key: first.case_key,
              result: payload,
              urls: {
                json: `/api/results/${target}/${first.case_key}/payload.json`,
                png: `/api/results/${target}/${first.case_key}/report.png`,
                csv: `/api/results/${target}/${first.case_key}/data.csv`,
              },
            },
          }));
          setParamsMap((prev) => ({ ...prev, [target]: first.params }));
        }
      }
    } catch { /* ignore */ }
  }, [results]);

  useEffect(() => {
    loadCached(lab);
  }, [lab, loadCached]);

  const handleRun = async (override?: Record<string, any>) => {
    const p = override ?? curParams;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/run/${lab}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p),
      });
      const data = (await res.json()) as LabResponse & { error?: string };
      if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
      setResults((prev) => ({ ...prev, [lab]: data }));
      setParamsMap((prev) => ({ ...prev, [lab]: data.result.params }));
      const cr = await fetch(`/api/cases/${lab}`);
      if (cr.ok) {
        const cd = (await cr.json()) as { cases?: LabSummary[] };
        setCachedMap((prev) => ({ ...prev, [lab]: cd.cases ?? [] }));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const setParam = (k: string, v: any) => {
    setParamsMap((prev) => ({ ...prev, [lab]: { ...prev[lab], [k]: v } }));
  };

  const payload = curRes?.result;
  const kpiEntries = Object.entries(payload?.kpis ?? {});
  const previewRows = payload?.table_preview ?? [];
  const previewCols = previewRows.length > 0 ? Object.keys(previewRows[0]) : [];

  return (
    <div className={`app-layout ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-top">
            <div className="brand-badge">{t.badge}</div>
            <div className="lang-switch">
              <button type="button" className={lang === 'zh' ? 'active' : ''} onClick={() => setLang('zh')}>中文</button>
              <button type="button" className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
            </div>
          </div>
          <h1>{t.title}</h1>
          <p>{t.subtitle}</p>
        </div>

        <div className="lab-tabs">
          {(['report', 'vehicle', 'pod', 'solver', 'deals'] as LabId[]).map((id) => (
            <button
              key={id}
              type="button"
              className={`lab-tab ${lab === id ? 'active' : ''}`}
              onClick={() => { setLab(id); setError(''); }}
            >
              {t.tabs[id]}
            </button>
          ))}
        </div>

        <div className="goal-banner">
          <Sparkles size={13} /> <span>{t.skills[lab]}</span>
        </div>

        <section className="panel-section">
          <div className="section-title"><Sliders size={14} /> {t.sectionParams}</div>

          {lab === 'report' && (
            <>
              <label className="select-row">
                <span>OpenFOAM Case</span>
                <select
                  value={curParams.case_type}
                  onChange={(e) => {
                    const ct = e.target.value;
                    setParamsMap((prev) => ({ ...prev, report: { case_type: ct, re_or_u: ct === 'step' ? 37500 : 2.0 } }));
                  }}
                >
                  <option value="step">Backward-Facing Step (分离 &amp; 回流)</option>
                  <option value="pipe">Turbulent Pipe Flow (压降 &amp; 速度剖面)</option>
                </select>
              </label>
              <label className="select-row">
                <span>{curParams.case_type === 'step' ? 'Reynolds Re_H' : 'Inlet Speed U (m/s)'}</span>
                {curParams.case_type === 'step' ? (
                  <select value={curParams.re_or_u} onChange={(e) => setParam('re_or_u', Number(e.target.value))}>
                    <option value={37500}>Re = 37,500 (Turbulent k-ω SST)</option>
                    <option value={400}>Re = 400 (Laminar)</option>
                  </select>
                ) : (
                  <select value={curParams.re_or_u} onChange={(e) => setParam('re_or_u', Number(e.target.value))}>
                    <option value={2.0}>2.0 m/s (Turbulent Re=100,000)</option>
                    <option value={4.0}>4.0 m/s (High-Re Re=200,000)</option>
                    <option value={0.03}>0.03 m/s (Laminar Poiseuille)</option>
                  </select>
                )}
              </label>
            </>
          )}

          {lab === 'vehicle' && (
            <>
              <label className="select-row">
                <span>年行驶里程 (km/year)</span>
                <select value={curParams.annual_km} onChange={(e) => setParam('annual_km', Number(e.target.value))}>
                  <option value={10000}>10,000 km/yr</option>
                  <option value={20000}>20,000 km/yr</option>
                  <option value={40000}>40,000 km/yr</option>
                </select>
              </label>
              <label className="select-row">
                <span>电价 (AUD/kWh)</span>
                <select value={curParams.elec_price} onChange={(e) => setParam('elec_price', Number(e.target.value))}>
                  <option value={0.25}>A$0.25 / kWh (Home Off-Peak)</option>
                  <option value={0.30}>A$0.30 / kWh (Melbourne Avg)</option>
                  <option value={0.55}>A$0.55 / kWh (Fast Supercharger)</option>
                </select>
              </label>
            </>
          )}

          {lab === 'pod' && (
            <>
              <label className="select-row">
                <span>障碍物截面 (pisoFoam 20 帧)</span>
                <select value={curParams.shape} onChange={(e) => setParam('shape', e.target.value)}>
                  <option value="cylinder">Circular Cylinder (经典卡门涡街)</option>
                  <option value="eureka">Melbourne Eureka Tower Cross-Section</option>
                </select>
              </label>
              <label className="select-row">
                <span>Reynolds Re</span>
                <select value={curParams.re} onChange={(e) => setParam('re', Number(e.target.value))}>
                  <option value={100}>Re = 100</option>
                  <option value={150}>Re = 150</option>
                  <option value={200}>Re = 200</option>
                </select>
              </label>
            </>
          )}

          {lab === 'solver' && (
            <>
              <label className="select-row">
                <span>Cavity Reynolds Re</span>
                <select value={curParams.re} onChange={(e) => setParam('re', Number(e.target.value))}>
                  <option value={100}>Re = 100</option>
                  <option value={400}>Re = 400 (Classic Benchmark)</option>
                  <option value={1000}>Re = 1,000</option>
                </select>
              </label>
              <label className="select-row">
                <span>网格分辨率 (Grid N×N)</span>
                <select value={curParams.grid_n} onChange={(e) => setParam('grid_n', Number(e.target.value))}>
                  <option value={49}>49 × 49 (Fast)</option>
                  <option value={65}>65 × 65 (Balanced)</option>
                  <option value={81}>81 × 81 (Fine)</option>
                </select>
              </label>
            </>
          )}

          {lab === 'deals' && (
            <>
              <label className="select-row">
                <span>超市过滤</span>
                <select value={curParams.store} onChange={(e) => setParam('store', e.target.value)}>
                  <option value="ALL">All (Coles + Woolworths)</option>
                  <option value="Coles">Coles Only</option>
                  <option value="Woolworths">Woolworths Only</option>
                </select>
              </label>
              <label className="select-row">
                <span>最低等效折扣率筛选</span>
                <select value={curParams.min_discount_pct} onChange={(e) => setParam('min_discount_pct', Number(e.target.value))}>
                  <option value={0}>全部 (All Deals)</option>
                  <option value={10}>&ge; 10% Off</option>
                  <option value={20}>&ge; 20% Off</option>
                </select>
              </label>
            </>
          )}

          <button type="button" className="run-btn" disabled={loading} onClick={() => handleRun()}>
            <Play size={15} /> {loading ? t.runningBtn : t.runBtn}
          </button>
        </section>

        {curRes && (
          <section className="panel-section">
            <a className="dl-btn" href={curRes.urls.png} download={`phase2_${lab}_${curRes.case_key}.png`}>
              <Download size={14} /> {t.downloadPng}
            </a>
            <a className="dl-btn" href={curRes.urls.csv} download={`phase2_${lab}_${curRes.case_key}.csv`}>
              <FileSpreadsheet size={14} /> {t.downloadCsv}
            </a>
          </section>
        )}

        <div className="sidebar-footer"><Flame size={13} /><span>Modal Cloud Python 3.11 + OpenFOAM v2512</span></div>
      </aside>

      <main className="workspace">
        <header className="kpi-bar">
          <button type="button" className="collapse-btn" onClick={() => setSidebarOpen((v) => !v)} title={sidebarOpen ? t.hideSidebar : t.showSidebar}>
            {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
          </button>
          <div className="kpi-grid">
            {kpiEntries.slice(0, 4).map(([kname, kval]) => (
              <div key={kname} className="kpi-card">
                <div className="kpi-label">{kname}</div>
                <div className="kpi-value gold">{String(kval)}</div>
              </div>
            ))}
            <div className="kpi-card">
              <div className="kpi-label">{curRes?.cached ? <Database size={13} /> : <Timer size={13} />} Cloud Status</div>
              <div className={`kpi-value ${curRes?.cached ? 'sage' : 'coral'}`}>
                {payload ? `${payload.timing_sec}s (${curRes?.cached ? 'KV' : 'Live'})` : '--'}
              </div>
            </div>
          </div>
        </header>

        {error && <div className="error-banner"><AlertCircle size={15} /><span>{error}</span></div>}

        <div className="content-scroll">
          {loading ? (
            <div className="loading-card">
              <div className="spinner" />
              <h3>{t.loadingTitle}</h3>
              <p>{t.loadingDesc}</p>
            </div>
          ) : payload ? (
            <>
              <div className="figure-card">
                <img src={`data:image/png;base64,${payload.image_b64}`} alt="Cloud Matplotlib Report" className="report-img" />
              </div>

              <div className="bottom-grid">
                <div className="data-card">
                  <div className="card-title"><Table2 size={14} /> {t.tableTitle}</div>
                  <div className="table-wrap">
                    <table className="pd-table">
                      <thead>
                        <tr>{previewCols.map((c) => <th key={c}>{c}</th>)}</tr>
                      </thead>
                      <tbody>
                        {previewRows.map((row, idx) => (
                          <tr key={idx}>{previewCols.map((c) => <td key={c}>{String(row[c])}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="data-card">
                  <div className="card-title-row">
                    <span className="card-title"><Code2 size={14} /> {t.codeTitle}</span>
                    <button
                      type="button"
                      className="copy-btn"
                      onClick={() => {
                        navigator.clipboard?.writeText(payload.code_snippet).catch(() => {});
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }}
                    >
                      {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? t.copied : t.copyCode}
                    </button>
                  </div>
                  <pre className="code-pre">{payload.code_snippet}</pre>
                </div>
              </div>
            </>
          ) : (
            <div className="loading-card"><h3>{t.emptyTitle}</h3></div>
          )}
        </div>

        {curCached.length > 0 && (
          <footer className="presets-strip">
            <span className="strip-label"><Database size={13} /> {t.cachedStrip}</span>
            <div className="strip-items">
              {curCached.map((c) => (
                <button
                  key={c.case_key}
                  type="button"
                  className={`case-chip ${c.case_key === curRes?.case_key ? 'active' : ''}`}
                  onClick={() => handleRun(c.params)}
                >
                  {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(' · ')} ({c.timing_sec}s)
                </button>
              ))}
            </div>
          </footer>
        )}
      </main>
    </div>
  );
};
