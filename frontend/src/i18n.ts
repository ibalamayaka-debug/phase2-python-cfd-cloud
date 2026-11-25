export type Lang = 'zh' | 'en';

export function detectInitialLang(): Lang {
  try {
    const q = new URLSearchParams(window.location.search).get('lang');
    if (q === 'zh' || q === 'en') return q;
    const saved = localStorage.getItem('p2_lang');
    if (saved === 'zh' || saved === 'en') return saved;
  } catch { /* ignore */ }
  if (typeof navigator !== 'undefined' && navigator.language) {
    return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en';
  }
  return 'zh';
}

export const TRANSLATIONS = {
  zh: {
    pageTitle: 'Phase 2：NumPy · Pandas · Matplotlib 云端仿真五合一实验室',
    badge: '100% Modal 云端 Python + OpenFOAM v2512',
    title: 'Python × 仿真科学计算云实验室',
    subtitle: 'NumPy 矩阵 · Pandas 日志与正则清洗 · Matplotlib 自动报告（全 5 个实战课题云端运行）',
    tabs: {
      report: '1. OpenFOAM 自动出图报告',
      vehicle: '2. 三车 Pandas 气动回归',
      pod: '3. 卡门涡街 SVD 模态分解',
      solver: '4. 纯 NumPy 手搓 CFD 求解器',
      deals: '5. Pandas 脏数据清洗超市折扣',
    },
    skills: {
      report: 'Matplotlib 报告三件套：残差收敛图 (semilogy) + 速度剖面 + 压力曲线 + Pandas 解析 log',
      vehicle: 'Pandas GroupBy 多工况对比 + NumPy 最小二乘拟合 P = k·v³ + 年省电费估算',
      pod: 'OpenFOAM pisoFoam 20 帧瞬态流场 × NumPy np.linalg.svd 奇异值能量衰减与主涡模态',
      solver: '纯 NumPy 数组切片矢量化 2D N-S 求解器 vs Python 嵌套循环提速倍比 + Ghia 基准校验',
      deals: 'Pandas + 正则 str.extractall 解析 Coles/Woolworths 满减规则与等效折扣榜',
    },
    runBtn: 'Modal 云端运行 Python + 仿真',
    runningBtn: '正在 Modal 云端求解与出图...',
    sectionParams: '实验参数控制',
    downloadPng: '下载 300-DPI 报告图 (.png)',
    downloadCsv: '下载清洗后数据集 (.csv)',
    tableTitle: 'Pandas 清洗 / 计算结果预览 (Top Rows)',
    codeTitle: '核心可复用 Phase 2 Python 代码',
    copyCode: '复制代码',
    copied: '已复制',
    cachedStrip: '云端已缓存实验（0ms 秒开）：',
    hideSidebar: '收起侧栏',
    showSidebar: '展开侧栏',
    loadingTitle: '正在 Modal 云端执行 Python (NumPy/Pandas/Matplotlib) + OpenFOAM...',
    loadingDesc: '全部计算与绘图均在云端容器完成，完成后自动返回高清图表与 CSV（约 5–25s）',
    emptyTitle: '选择一个实验课题并点击“Modal 云端运行 Python + 仿真”',
  },
  en: {
    pageTitle: 'Phase 2: NumPy · Pandas · Matplotlib Cloud Simulation Lab',
    badge: '100% Modal Cloud Python + OpenFOAM v2512',
    title: 'Python × Simulation Cloud Studio',
    subtitle: 'NumPy Linear Algebra · Pandas Cleaning · Matplotlib Auto-Reports (All 5 Labs in Cloud)',
    tabs: {
      report: '1. OpenFOAM Auto-Report Plots',
      vehicle: '2. 3-Car Pandas & OLS Aero',
      pod: '3. Vortex Wake NumPy SVD POD',
      solver: '4. Vectorized NumPy CFD Solver',
      deals: '5. Pandas Regex Deals Cleaning',
    },
    skills: {
      report: 'Matplotlib Trio: Residual Convergence (semilogy) + Velocity Profile + Pressure Curve + Log Parser',
      vehicle: 'Pandas GroupBy multi-case matrix + NumPy v^3 OLS regression + Annual energy savings',
      pod: 'OpenFOAM pisoFoam 20-snapshot wake × NumPy np.linalg.svd singular value spectrum & POD modes',
      solver: 'Pure NumPy array-slicing 2D Navier-Stokes vs naive loop speedup + Ghia (1982) validation',
      deals: 'Pandas regex extraction across messy Coles/Woolworths promos -> Discount % leaderboard',
    },
    runBtn: 'Run Python + Sim on Modal',
    runningBtn: 'Running on Modal Cloud...',
    sectionParams: 'Experiment Parameters',
    downloadPng: 'Download 300-DPI Figure (.png)',
    downloadCsv: 'Download Clean Dataset (.csv)',
    tableTitle: 'Pandas Processed Table Preview',
    codeTitle: 'Reproducible Phase 2 Python Snippet',
    copyCode: 'Copy Code',
    copied: 'Copied',
    cachedStrip: 'Cached Cloud Experiments (Instant):',
    hideSidebar: 'Hide sidebar',
    showSidebar: 'Show sidebar',
    loadingTitle: 'Running Python + OpenFOAM on Modal Cloud...',
    loadingDesc: 'Solving physics, cleaning with Pandas & rendering 300-DPI Matplotlib report (~5–25s)',
    emptyTitle: 'Select a lab and click "Run Python + Sim on Modal"',
  },
} as const;
