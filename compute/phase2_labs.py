"""
Phase 2 Python + Simulation 5-in-1 Cloud Compute Modules (Modal OpenFOAM + NumPy + Pandas + Matplotlib):
  1. run_openfoam_report_lab  : OpenFOAM log/VTK parsing -> Pandas DataFrame -> Matplotlib 3-panel report
  2. run_vehicle_analytics_lab: Live Vehicle FSI CSV/API -> Pandas groupby + NumPy v^3 OLS -> Matplotlib
  3. run_pod_svd_lab          : OpenFOAM pisoFoam transient vortex wake -> NumPy SVD POD modes -> Matplotlib
  4. run_numpy_solver_lab     : Pure NumPy vectorized 2D NS Cavity solver vs Ghia (1982) + speedup timing
  5. run_deals_pandas_lab     : Live Coles & WWS messy text regex cleaning in Pandas -> Matplotlib strategy
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve

# Crisp dark studio theme for every generated report figure (with CJK fallback font installed via apt)
plt.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = "#161412"
plt.rcParams["axes.facecolor"] = "#1f1b17"
plt.rcParams["axes.edgecolor"] = "#4a3f35"
plt.rcParams["axes.labelcolor"] = "#f5ece2"
plt.rcParams["xtick.color"] = "#cbb8a5"
plt.rcParams["ytick.color"] = "#cbb8a5"
plt.rcParams["text.color"] = "#fdf6ee"
plt.rcParams["grid.color"] = "#382f27"
plt.rcParams["grid.linestyle"] = "--"
plt.rcParams["grid.alpha"] = 0.65

OPENFOAM_BASHRC_CANDIDATES = [
    os.environ.get("OPENFOAM_BASHRC", ""),
    "/usr/lib/openfoam/openfoam2512/etc/bashrc",
    "/usr/lib/openfoam/openfoam2412/etc/bashrc",
    "/opt/openfoam2512/etc/bashrc",
]


def _find_bashrc() -> Optional[str]:
    for p in OPENFOAM_BASHRC_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return None


def _run_foam(case_dir: Path, cmd: str, timeout: int = 180) -> str:
    bashrc = _find_bashrc()
    full_cmd = f"source '{bashrc}' >/dev/null 2>&1 || true; {cmd}" if bashrc else cmd
    proc = subprocess.run(
        ["bash", "-lc", full_cmd],
        cwd=str(case_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-25:])
        raise RuntimeError(f"OpenFOAM failed ({cmd}):\n{tail}")
    return proc.stdout


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ==============================================================================
# LAB 1: OpenFOAM Auto-Report Generator (Convergence + Pressure + Velocity)
# ==============================================================================

def run_openfoam_report_lab(case_type: str = "step", re_or_u: float = 37500.0) -> Dict[str, Any]:
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    t0 = time.perf_counter()
    ct = "pipe" if case_type.lower().strip() == "pipe" else "step"
    key = hashlib.sha256(f"p2|report|{ct}|{re_or_u:.2f}".encode()).hexdigest()[:16]

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"p2_rep_{ct}_"))
    try:
        for sub in ("0", "constant", "system"):
            (tmp_dir / sub).mkdir(parents=True, exist_ok=True)

        if ct == "step":
            re_val = min((400, 37500), key=lambda x: abs(x - re_or_u))
            u_in = 10.0
            H = 1.0
            rho = 1.225
            nu = (u_in * H) / re_val
            is_turb = re_val >= 2300
            k_in = 1.5 * (u_in * 0.04) ** 2
            omega_in = math.sqrt(k_in) / (0.09 ** 0.25 * 0.07 * H)

            (tmp_dir / "system" / "blockMeshDict").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object blockMeshDict; }
scale 1;
vertices
(
    (-4 1 0) (-4 2 0) (0 0 0) (0 1 0) (0 2 0) (22 0 0) (22 1 0) (22 2 0)
    (-4 1 0.1) (-4 2 0.1) (0 0 0.1) (0 1 0.1) (0 2 0.1) (22 0 0.1) (22 1 0.1) (22 2 0.1)
);
blocks
(
    hex (0 3 4 1 8 11 12 9) (32 24 1) simpleGrading (0.4 ((0.5 0.5 3.0) (0.5 0.5 0.333)) 1)
    hex (3 6 7 4 11 14 15 12) (110 24 1) simpleGrading (4.0 ((0.5 0.5 3.0) (0.5 0.5 0.333)) 1)
    hex (2 5 6 3 10 13 14 11) (110 24 1) simpleGrading (4.0 ((0.5 0.5 3.5) (0.5 0.5 0.285)) 1)
);
edges ();
boundary
(
    inlet { type patch; faces ((0 1 9 8)); }
    outlet { type patch; faces ((5 13 14 6) (6 14 15 7)); }
    upperWall { type wall; faces ((1 4 12 9) (4 7 15 12)); }
    lowerWall { type wall; faces ((0 8 11 3) (3 11 10 2) (2 10 13 5)); }
    frontAndBack { type empty; faces ((0 3 4 1) (3 6 7 4) (2 5 6 3) (8 9 12 11) (11 12 15 14) (10 11 14 13)); }
);
mergePatchPairs ();
""")
            (tmp_dir / "system" / "controlDict").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object controlDict; }
application simpleFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 600;
deltaT 1; writeControl timeStep; writeInterval 600; purgeWrite 1;
writeFormat binary; writePrecision 8; writeCompression off; timeFormat general; timePrecision 6;
""")
            (tmp_dir / "system" / "fvSchemes").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
wallDist { method meshWave; }
""")
            (tmp_dir / "system" / "fvSolution").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-6; relTol 0.05; }
    "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-6; relTol 0.1; }
}
SIMPLE { nNonOrthogonalCorrectors 0; consistent yes; residualControl { p 1e-5; U 1e-5; "(k|omega)" 1e-5; } }
relaxationFactors { fields { p 0.3; } equations { U 0.7; k 0.6; omega 0.6; } }
""")
            (tmp_dir / "constant" / "transportProperties").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian; nu [0 2 -1 0 0 0 0] {nu:.8e};
""")
            (tmp_dir / "constant" / "turbulenceProperties").write_text(
                """FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType RAS; RAS { RASModel kOmegaSST; turbulence on; printCoeffs off; }
""" if is_turb else """FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
"""
            )
            (tmp_dir / "0" / "U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({u_in} 0 0);
boundaryField
{{
    inlet {{ type fixedValue; value uniform ({u_in} 0 0); }}
    outlet {{ type inletOutlet; inletValue uniform (0 0 0); value uniform ({u_in*0.5} 0 0); }}
    upperWall {{ type noSlip; }}
    lowerWall {{ type noSlip; }}
    frontAndBack {{ type empty; }}
}}
""")
            (tmp_dir / "0" / "p").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type zeroGradient; } outlet { type fixedValue; value uniform 0; } upperWall { type zeroGradient; } lowerWall { type zeroGradient; } frontAndBack { type empty; } }
""")
            if is_turb:
                for fn, dim, val, wtype in (
                    ("k", "[0 2 -2 0 0 0 0]", k_in, "kqRWallFunction"),
                    ("omega", "[0 0 -1 0 0 0 0]", omega_in, "omegaWallFunction"),
                ):
                    (tmp_dir / "0" / fn).write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object {fn}; }}
dimensions {dim}; internalField uniform {val:.6e};
boundaryField {{ inlet {{ type fixedValue; value uniform {val:.6e}; }} outlet {{ type inletOutlet; inletValue uniform {val:.6e}; value uniform {val:.6e}; }} upperWall {{ type {wtype}; value uniform {val:.6e}; }} lowerWall {{ type {wtype}; value uniform {val:.6e}; }} frontAndBack {{ type empty; }} }}
""")
                (tmp_dir / "0" / "nut").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object nut; }
dimensions [0 2 -1 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type calculated; value uniform 0; } outlet { type calculated; value uniform 0; } upperWall { type nutkWallFunction; value uniform 0; } lowerWall { type nutkWallFunction; value uniform 0; } frontAndBack { type empty; } }
""")
        else:
            # Turbulent Pipe Flow (DN50, L = 32D)
            u_in = min((0.03, 2.0, 4.0), key=lambda x: abs(x - re_or_u))
            D = 0.05
            R = 0.5 * D
            L = 32.0 * D
            nu = 1.0e-6
            rho = 998.2
            Re = u_in * D / nu
            is_turb = Re >= 2300
            k_in = max(1.5 * (u_in * 0.16 * max(Re, 2300.0) ** (-0.125)) ** 2, 1e-6)
            omega_in = max(math.sqrt(k_in) / (0.09 ** 0.25 * 0.07 * D), 0.1)

            a, c = 0.36 * R, R / math.sqrt(2.0)
            pts2d = [(-a, -a), (+a, -a), (+a, +a), (-a, +a), (-c, -c), (+c, -c), (+c, +c), (-c, +c)]
            v_lines = [f"    ({xv:.7g} {yv:.7g} {zv:.7g})" for xv in (0.0, L) for (yv, zv) in pts2d]
            arcs = [(4, 5, 0.0, -R), (5, 6, +R, 0.0), (6, 7, 0.0, +R), (7, 4, -R, 0.0)]
            e_lines = [f"    arc {s*8+i0} {s*8+i1} ({xv:.7g} {ym:.7g} {zm:.7g})" for s, xv in enumerate((0.0, L)) for i0, i1, ym, zm in arcs]
            (tmp_dir / "system" / "blockMeshDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
scale 1;
vertices ( {chr(10).join(v_lines)} );
blocks
(
    hex (0 1 2 3 8 9 10 11) (6 6 70) simpleGrading (1 1 1)
    hex (4 5 1 0 12 13 9 8) (6 6 70) simpleGrading (1 4.0 1)
    hex (1 5 6 2 9 13 14 10) (6 6 70) simpleGrading (0.25 1 1)
    hex (3 2 6 7 11 10 14 15) (6 6 70) simpleGrading (1 0.25 1)
    hex (4 0 3 7 12 8 11 15) (6 6 70) simpleGrading (4.0 1 1)
);
edges ( {chr(10).join(e_lines)} );
boundary
(
    inlet {{ type patch; faces ((0 3 2 1) (4 0 1 5) (1 2 6 5) (3 7 6 2) (4 7 3 0)); }}
    outlet {{ type patch; faces ((8 9 10 11) (12 13 9 8) (9 13 14 10) (11 10 14 15) (12 8 11 15)); }}
    walls {{ type wall; faces ((4 5 13 12) (5 6 14 13) (6 7 15 14) (7 4 12 15)); }}
);
mergePatchPairs ();
""")
            (tmp_dir / "system" / "controlDict").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object controlDict; }
application simpleFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 500;
deltaT 1; writeControl timeStep; writeInterval 500; purgeWrite 1;
writeFormat binary; writePrecision 8; writeCompression off; timeFormat general; timePrecision 6;
""")
            (tmp_dir / "system" / "fvSchemes").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U); div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""")
            (tmp_dir / "system" / "fvSolution").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers { p { solver GAMG; smoother GaussSeidel; tolerance 1e-6; relTol 0.05; } "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-6; relTol 0.1; } }
SIMPLE { nNonOrthogonalCorrectors 0; consistent yes; residualControl { p 1e-5; U 1e-5; "(k|omega)" 1e-5; } }
relaxationFactors { fields { p 0.3; } equations { U 0.7; k 0.7; omega 0.7; } }
""")
            (tmp_dir / "constant" / "transportProperties").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian; nu [0 2 -1 0 0 0 0] {nu:.6e};
""")
            (tmp_dir / "constant" / "turbulenceProperties").write_text(
                """FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType RAS; RAS { RASModel kOmegaSST; turbulence on; printCoeffs off; }
""" if is_turb else """FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
"""
            )
            (tmp_dir / "0" / "U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({u_in} 0 0);
boundaryField {{ inlet {{ type fixedValue; value uniform ({u_in} 0 0); }} outlet {{ type zeroGradient; }} walls {{ type noSlip; }} }}
""")
            (tmp_dir / "0" / "p").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type zeroGradient; } outlet { type fixedValue; value uniform 0; } walls { type zeroGradient; } }
""")
            if is_turb:
                for fn, dim, val, wtype in (
                    ("k", "[0 2 -2 0 0 0 0]", k_in, "kqRWallFunction"),
                    ("omega", "[0 0 -1 0 0 0 0]", omega_in, "omegaWallFunction"),
                ):
                    (tmp_dir / "0" / fn).write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object {fn}; }}
dimensions {dim}; internalField uniform {val:.6e};
boundaryField {{ inlet {{ type fixedValue; value uniform {val:.6e}; }} outlet {{ type zeroGradient; }} walls {{ type {wtype}; value uniform {val:.6e}; }} }}
""")
                (tmp_dir / "0" / "nut").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object nut; }
dimensions [0 2 -1 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type calculated; value uniform 0; } outlet { type calculated; value uniform 0; } walls { type nutkWallFunction; value uniform 0; } }
""")

        _run_foam(tmp_dir, "blockMesh", timeout=60)
        log_txt = _run_foam(tmp_dir, "simpleFoam", timeout=180)
        _run_foam(tmp_dir, "foamToVTK -latestTime -noFaceZones", timeout=90)

        # Parse real OpenFOAM residual log into Pandas DataFrame!
        rows = []
        cur_t = 0
        rec: Dict[str, Any] = {}
        for line in log_txt.splitlines():
            mt = re.match(r"^Time\s*=\s*(\d+)", line.strip())
            if mt:
                if rec:
                    rows.append(rec)
                cur_t = int(mt.group(1))
                rec = {"iter": cur_t}
                continue
            mr = re.search(r"Solving for (\w+), Initial residual = ([\d.eE+-]+)", line)
            if mr and mr.group(1) not in rec:
                rec[mr.group(1)] = float(mr.group(2))
        if rec and len(rec) > 1:
            rows.append(rec)

        df_res = pd.DataFrame(rows).sort_values("iter").reset_index(drop=True)

        # Read VTK volume & extract Velocity Profile + Pressure Curve
        vtu_path = sorted((tmp_dir / "VTK").rglob("internal.vtu"), key=lambda p: p.stat().st_mtime)[-1]
        r_vtu = vtk.vtkXMLUnstructuredGridReader()
        r_vtu.SetFileName(str(vtu_path))
        r_vtu.Update()
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(r_vtu.GetOutput())
        c2p.Update()
        ug_pt = c2p.GetOutput()

        def probe(pts):
            poly = vtk.vtkPolyData()
            vp = vtk.vtkPoints()
            for x, y, z in pts:
                vp.InsertNextPoint(float(x), float(y), float(z))
            poly.SetPoints(vp)
            pr = vtk.vtkProbeFilter()
            pr.SetInputData(poly)
            pr.SetSourceData(ug_pt)
            pr.Update()
            return pr.GetOutput().GetPointData()

        fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2))
        fig.suptitle(
            f"OpenFOAM 自动工程报告 · {'后台阶流动 (Backward-Facing Step)' if ct == 'step' else '圆管流动 (Pipe Flow)'}",
            fontsize=14,
            fontweight="bold",
            color="#fbbf24",
            y=0.98,
        )

        # Panel 1: Convergence Chart (Pandas + Matplotlib semilogy)
        ax1 = axes[0, 0]
        for col, color in (("p", "#f97316"), ("Ux", "#38bdf8"), ("Uy", "#22c55e"), ("k", "#e879f9"), ("omega", "#fbbf24")):
            if col in df_res.columns:
                valid = df_res[col].dropna()
                if len(valid) > 0:
                    ax1.semilogy(df_res.loc[valid.index, "iter"], valid, label=col, color=color, lw=2.0)
        ax1.axhline(1e-5, color="#fb7185", ls=":", lw=1.2, label="Target 1e-5")
        ax1.set_title("1. 收敛残差曲线 (Convergence Chart)")
        ax1.set_xlabel("Iteration Step")
        ax1.set_ylabel("Initial Residual (log)")
        ax1.grid(True)
        ax1.legend(fontsize=8.5, ncol=3, framealpha=0.25)

        if ct == "step":
            ys = np.linspace(0.02, 1.98, 50)
            ax2 = axes[0, 1]
            for x_loc, col in ((1.0, "#fb7185"), (4.0, "#fbbf24"), (8.0, "#22c55e"), (14.0, "#38bdf8")):
                pd_p = probe([(x_loc, y, 0.05) for y in ys])
                ux = vtk_to_numpy(pd_p.GetArray("U"))[:, 0] / u_in
                ax2.plot(ux, ys, lw=2.1, color=col, label=f"x/H = {int(x_loc)}")
            ax2.axvline(0.0, color="#cbb8a5", ls="--", lw=1.0)
            ax2.set_title("2. 多截面速度剖面 (Velocity Profiles)")
            ax2.set_xlabel("Normalized Velocity u_x / U_in")
            ax2.set_ylabel("Height y / H")
            ax2.grid(True)
            ax2.legend(fontsize=8.5, framealpha=0.25)

            xs_wall = np.linspace(0.1, 20.0, 90)
            pd_w = probe([(x, 0.04, 0.05) for x in xs_wall])
            p_ref = float(vtk_to_numpy(probe([(-0.5, 1.5, 0.05)]).GetArray("p"))[0])
            u_wall = vtk_to_numpy(pd_w.GetArray("U"))[:, 0] / u_in
            p_wall = (vtk_to_numpy(pd_w.GetArray("p")) - p_ref) * rho / (0.5 * rho * u_in ** 2)
            xr_h = 6.2
            for i in range(5, len(xs_wall)):
                if u_wall[i - 1] < 0 <= u_wall[i]:
                    xr_h = float(xs_wall[i - 1] + (-u_wall[i - 1] / max(u_wall[i] - u_wall[i - 1], 1e-9)) * (xs_wall[i] - xs_wall[i - 1]))
                    break

            ax3 = axes[1, 0]
            ax3.plot(xs_wall, p_wall, color="#a78bfa", lw=2.2, label="Wall Cp(x)")
            ax3.plot(xs_wall, u_wall, color="#38bdf8", lw=2.0, label="Near-Wall u_x/U_in")
            ax3.fill_between(xs_wall, u_wall, 0, where=(u_wall < 0), color="#fb7185", alpha=0.28, label="回流区 u<0")
            ax3.scatter([xr_h], [0.0], color="#fbbf24", s=65, zorder=5, label=f"再附着点 xR/H={xr_h:.2f}")
            ax3.axhline(0, color="#cbb8a5", lw=0.9)
            ax3.set_title("3. 压力恢复 Cp 与分离回流区间 (Pressure & Separation)")
            ax3.set_xlabel("Downstream x / H")
            ax3.set_ylabel("Cp / Near-wall Velocity Ratio")
            ax3.grid(True)
            ax3.legend(fontsize=8.5, framealpha=0.25)

            df_export = pd.DataFrame({"x_over_H": np.round(xs_wall, 3), "u_wall_ratio": np.round(u_wall, 4), "cp_wall": np.round(p_wall, 4)})
            kpis = {"reynolds": int(re_val), "iterations": int(df_res["iter"].max()), "xr_h": round(xr_h, 2), "cp_max": round(float(np.max(p_wall)), 3), "final_p_res": float(df_res["p"].dropna().iloc[-1])}
        else:
            r_norm = np.linspace(-0.98, 0.98, 45)
            pd_r = probe([(29.0 * D, rn * R, 0.0) for rn in r_norm])
            u_rad = np.maximum(vtk_to_numpy(pd_r.GetArray("U"))[:, 0], 0.0)
            u_max = max(float(np.max(u_rad)), 1e-6)
            u_norm = u_rad / u_max

            ax2 = axes[0, 1]
            ax2.plot(r_norm, u_norm, color="#38bdf8", lw=2.4, label="OpenFOAM Cloud CFD")
            ax2.plot(r_norm, (1.0 - np.abs(r_norm)) ** (1.0 / 7.0), color="#fbbf24", ls="--", lw=1.8, label="1/7th Power Law")
            ax2.plot(r_norm, 1.0 - r_norm ** 2, color="#fb7185", ls=":", lw=1.5, label="Laminar Poiseuille")
            ax2.set_title("2. 充分发展径向速度分布 (Velocity Profile u(r)/Umax)")
            ax2.set_xlabel("Radial Position r / R")
            ax2.set_ylabel("u / Umax")
            ax2.grid(True)
            ax2.legend(fontsize=8.5, framealpha=0.25)

            xs_ax = np.linspace(0.02 * L, 0.98 * L, 40)
            pd_ax = probe([(x, 0.0, 0.0) for x in xs_ax])
            p_pa = vtk_to_numpy(pd_ax.GetArray("p")) * rho
            m_dev = xs_ax >= 12.0 * D
            slope, intercept = np.polyfit(xs_ax[m_dev], p_pa[m_dev], 1)
            dp_dx = max(-float(slope), 0.0)
            f_cfd = (dp_dx * D) / max(0.5 * rho * u_in ** 2, 1e-9)

            ax3 = axes[1, 0]
            ax3.plot(xs_ax / D, p_pa, "o-", ms=3.5, color="#f97316", lw=2.0, label="OpenFOAM Centerline p(x)")
            ax3.plot(xs_ax[m_dev] / D, slope * xs_ax[m_dev] + intercept, "--", color="#22c55e", lw=2.0, label=f"Polyfit |dP/dx|={dp_dx:.1f} Pa/m")
            ax3.set_title("3. 沿程压降曲线 (Pressure Drop Curve)")
            ax3.set_xlabel("Axial Distance x / D")
            ax3.set_ylabel("Static Pressure p (Pa)")
            ax3.grid(True)
            ax3.legend(fontsize=8.5, framealpha=0.25)

            df_export = pd.DataFrame({"x_over_D": np.round(xs_ax / D, 2), "pressure_pa": np.round(p_pa, 3)})
            kpis = {"reynolds": round(Re, 0), "iterations": int(df_res["iter"].max()), "dp_dx_pam": round(dp_dx, 2), "darcy_f_cfd": round(f_cfd, 4), "final_p_res": float(df_res["p"].dropna().iloc[-1])}

        # Panel 4: Executive KPI Summary Box
        ax4 = axes[1, 1]
        ax4.axis("off")
        summary_lines = [
            f"算例类型: {'Backward-Facing Step' if ct == 'step' else 'DN50 Circular Pipe'}",
            f"雷诺数 Re: {kpis['reynolds']:,}",
            f"收敛迭代步数: {kpis['iterations']} steps",
            f"最终压力残差: {kpis['final_p_res']:.2e}",
            f"关键特征 KPI: {'再附着点 xR/H = ' + str(kpis['xr_h']) if ct == 'step' else '压降梯度 = ' + str(kpis['dp_dx_pam']) + ' Pa/m'}",
            f"Pandas 清洗日志行数: {len(df_res)} rows",
            f"云端端到端总耗时: {time.perf_counter() - t0:.2f} s",
        ]
        ax4.text(0.06, 0.85, "4. Pandas 自动统计与报告摘要", fontsize=12.5, fontweight="bold", color="#fbbf24")
        for idx, line in enumerate(summary_lines):
            ax4.text(0.08, 0.70 - idx * 0.10, f"•  {line}", fontsize=10.5, color="#f5ece2")

        plt.tight_layout(rect=[0, 0, 1, 0.94])
        img_b64 = _fig_to_b64(fig)

        code_snippet = """# Phase 2 核心代码：Pandas 解析 OpenFOAM 日志 + Matplotlib 一键出图
import re, pandas as pd, matplotlib.pyplot as plt
rows = []
for line in open("log.simpleFoam"):
    m = re.search(r"Solving for (\\w+), Initial residual = ([\\d.eE+-]+)", line)
    if m: rows.append({"field": m.group(1), "res": float(m.group(2))})
df = pd.DataFrame(rows)
fig, ax = plt.subplots()
for fld, grp in df.groupby("field"):
    ax.semilogy(grp["res"].values, label=fld)
ax.legend(); fig.savefig("convergence_report.png", dpi=300)"""

        return {
            "case_key": key,
            "lab": "report",
            "params": {"case_type": ct, "re_or_u": re_or_u},
            "kpis": kpis,
            "image_b64": img_b64,
            "csv_content": df_export.to_csv(index=False),
            "table_preview": df_res.tail(10).round(7).to_dict(orient="records"),
            "code_snippet": code_snippet,
            "timing_sec": round(time.perf_counter() - t0, 2),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# LAB 2: 3-Car Pandas & NumPy Aero Regression + Annual Cost Comparison
# ==============================================================================

def run_vehicle_analytics_lab(annual_km: float = 20000.0, elec_price: float = 0.30) -> Dict[str, Any]:
    t0 = time.perf_counter()
    akm = min(max(float(annual_km), 5000.0), 80000.0)
    ep = min(max(float(elec_price), 0.10), 1.00)
    key = hashlib.sha256(f"p2|vehicle|km={akm:.0f}|p={ep:.2f}".encode()).hexdigest()[:16]

    raw = _fetch_json("https://suv-fsi-worker.ibalamayaka.workers.dev/api/cases")
    rows = []
    for c in raw.get("cases", []):
        p = c.get("params", {})
        k = c.get("kpis", {})
        veh_id = p.get("vehicle", "boxy_suv")
        label = {"model3": "Tesla Model 3", "tiggo4": "Chery Tiggo 4", "boxy_suv": "Luxury Boxy SUV"}.get(veh_id, veh_id)
        rows.append({
            "vehicle": label,
            "speed_kmh": float(p.get("speed_kmh", 120)),
            "road_g": float(p.get("road_g", 1.6)),
            "material": str(p.get("material", "ahss")).upper(),
            "cd": float(k.get("cd", 0.35)),
            "drag_n": float(k.get("drag_n", 500)),
            "aero_power_kw": float(k.get("aero_power_kw", 20)),
            "stress_mpa": float(k.get("max_von_mises_mpa", 16)),
            "strain_micro": float(k.get("max_strain_micro", 100)),
            "dofs": int(k.get("n_fem_dofs", 55000)),
        })
    df = pd.DataFrame(rows)

    # Speed sweep & NumPy Linear Algebra OLS fit: P_aero = coef * v^3
    speeds = np.array([60.0, 80.0, 100.0, 120.0, 160.0, 200.0])
    veh_specs = {"Tesla Model 3": (0.324, 2.22, "#38bdf8"), "Chery Tiggo 4": (0.345, 2.48, "#22c55e"), "Luxury Boxy SUV": (0.581, 2.85, "#fb7185")}

    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2))
    fig.suptitle(
        f"三车云算气动-结构 Pandas/NumPy 对比分析（年行驶 {akm:,.0f} km @ ${ep:.2f}/kWh）",
        fontsize=13.5,
        fontweight="bold",
        color="#fbbf24",
        y=0.98,
    )

    ax1 = axes[0, 0]
    fit_coeffs = {}
    annual_costs = {}
    for vname, (cd_val, area_val, col) in veh_specs.items():
        v_ms = speeds / 3.6
        p_kw = 0.5 * 1.225 * cd_val * area_val * (v_ms ** 3) / 1000.0
        # NumPy least-squares fit: P = k * v_kmh^3
        X = (speeds ** 3)[:, None]
        coef, *_ = np.linalg.lstsq(X, p_kw, rcond=None)
        fit_coeffs[vname] = float(coef[0])
        v_dense = np.linspace(60, 205, 80)
        ax1.plot(v_dense, fit_coeffs[vname] * v_dense ** 3, color=col, lw=2.2, label=f"{vname} (Cd={cd_val})")
        # Overlay real cloud Modal OpenFOAM runs
        sub_real = df[df["vehicle"] == vname]
        if not sub_real.empty:
            ax1.scatter(sub_real["speed_kmh"], sub_real["aero_power_kw"], color=col, s=55, edgecolor="#fff", zorder=5)
        # 110 km/h highway energy cost over annual_km
        p110 = 0.5 * 1.225 * cd_val * area_val * ((110.0 / 3.6) ** 3) / 1000.0
        kwh_yr = (p110 / 0.88) * (akm / 110.0)
        annual_costs[vname] = round(kwh_yr * ep, 1)

    ax1.set_title("1. NumPy 最小二乘三次方拟合 P = k·v³ (圆点=真实云算)")
    ax1.set_xlabel("Speed (km/h)")
    ax1.set_ylabel("Aerodynamic Drag Power (kW)")
    ax1.grid(True)
    ax1.legend(fontsize=8.5, framealpha=0.25)

    # Panel 2: Pandas groupby 120 km/h Drag Force
    ax2 = axes[0, 1]
    d120 = df[df["speed_kmh"] == 120.0].groupby("vehicle", as_index=False)["drag_n"].mean().sort_values("drag_n")
    bars = ax2.barh(d120["vehicle"], d120["drag_n"], color=["#38bdf8", "#22c55e", "#fb7185"][: len(d120)])
    for b in bars:
        ax2.text(b.get_width() + 18, b.get_y() + b.get_height() / 2, f"{b.get_width():.0f} N", va="center", fontsize=9.5)
    ax2.set_xlim(0, max(d120["drag_n"].max() * 1.22, 100))
    ax2.set_title("2. 120 km/h 实算气动阻力对比 (Pandas GroupBy)")
    ax2.set_xlabel("Drag Force (N)")
    ax2.grid(True, axis="x")

    # Panel 3: Material Stress vs Strain
    ax3 = axes[1, 0]
    mat_df = df.groupby("material", as_index=False)[["stress_mpa", "strain_micro"]].mean()
    x_idx = np.arange(len(mat_df))
    ax3.bar(x_idx - 0.18, mat_df["stress_mpa"], width=0.35, color="#f97316", label="Stress σ_vM (MPa)")
    ax3_r = ax3.twinx()
    ax3_r.bar(x_idx + 0.18, mat_df["strain_micro"] / 10.0, width=0.35, color="#a78bfa", label="Strain (×10 με)")
    ax3.set_xticks(x_idx)
    ax3.set_xticklabels(mat_df["material"])
    ax3.set_title("3. 白车身材料应力 vs 应变均值对比")
    ax3.set_ylabel("von Mises Stress (MPa)", color="#f97316")
    ax3_r.set_ylabel("Equivalent Strain (×10 με)", color="#a78bfa")
    ax3.grid(True, axis="y")

    # Panel 4: Annual Highway Energy Cost AUD
    ax4 = axes[1, 1]
    names = list(annual_costs.keys())
    vals = [annual_costs[n] for n in names]
    b4 = ax4.bar(names, vals, color=["#38bdf8", "#22c55e", "#fb7185"])
    for b in b4:
        ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + 8, f"A${b.get_height():.0f}", ha="center", fontsize=9.5)
    ax4.set_ylim(0, max(vals) * 1.22)
    ax4.set_title(f"4. 年行驶 {akm:,.0f} km 气动克服电费估算 (AUD)")
    ax4.set_ylabel("Annual Aero Cost (AUD)")
    ax4.grid(True, axis="y")

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    img_b64 = _fig_to_b64(fig)

    m3_cost = annual_costs["Tesla Model 3"]
    suv_cost = annual_costs["Luxury Boxy SUV"]
    kpis = {
        "n_cloud_cases": int(len(df)),
        "model3_vs_suv_saving_pct": round((1.0 - m3_cost / suv_cost) * 100.0, 1),
        "annual_saving_aud": round(suv_cost - m3_cost, 1),
        "tiggo4_power_120kw": round(fit_coeffs["Chery Tiggo 4"] * (120.0 ** 3), 2),
        "model3_power_120kw": round(fit_coeffs["Tesla Model 3"] * (120.0 ** 3), 2),
    }
    code_snippet = """# Pandas 读取云端三车 FSI 数据 + NumPy 最小二乘拟合 v^3 功耗
import numpy as np, pandas as pd
df = pd.read_csv("https://powerbi-portfolio-cloud.ibalamayaka.workers.dev/api/export/engineering.csv")
auto = df[df["domain"] == "Automotive FSI"]
summary = auto.groupby("model_name")[["cd", "aero_power_kw", "stress_mpa"]].mean()
X = (auto["speed_kmh"].values ** 3)[:, None]
k_fit, *_ = np.linalg.lstsq(X, auto["aero_power_kw"].values, rcond=None)"""

    return {
        "case_key": key,
        "lab": "vehicle",
        "params": {"annual_km": akm, "elec_price": ep},
        "kpis": kpis,
        "image_b64": img_b64,
        "csv_content": df.to_csv(index=False),
        "table_preview": df.to_dict(orient="records"),
        "code_snippet": code_snippet,
        "timing_sec": round(time.perf_counter() - t0, 2),
    }


# ==============================================================================
# LAB 3: OpenFOAM Transient Karman Wake + NumPy SVD POD Modal Decomposition
# ==============================================================================

def run_pod_svd_lab(shape: str = "cylinder", reynolds: float = 150.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    sh = shape if shape in ("cylinder", "eureka") else "cylinder"
    re_val = min(max(float(reynolds), 80.0), 220.0)
    key = hashlib.sha256(f"p2|pod|{sh}|{re_val:.0f}".encode()).hexdigest()[:16]

    nx, ny = 150, 60
    x_min, x_max = -3.0, 14.0
    y_min, y_max = -3.5, 3.5
    dx, dy = (x_max - x_min) / nx, (y_max - y_min) / ny

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"p2_pod_{sh}_"))
    try:
        for sub in ("constant", "system"):
            (tmp_dir / sub).mkdir(parents=True, exist_ok=True)
        nu = 1.0 / re_val

        (tmp_dir / "system" / "blockMeshDict").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
scale 1;
vertices
(
    ({x_min} {y_min} -0.05) ({x_max} {y_min} -0.05) ({x_max} {y_max} -0.05) ({x_min} {y_max} -0.05)
    ({x_min} {y_min}  0.05) ({x_max} {y_min}  0.05) ({x_max} {y_max}  0.05) ({x_min} {y_max}  0.05)
);
blocks ( hex (0 1 2 3 4 5 6 7) ({nx} {ny} 1) simpleGrading (1 1 1) );
edges ();
boundary
(
    inlet {{ type patch; faces ((0 4 7 3)); }}
    outlet {{ type patch; faces ((1 2 6 5)); }}
    topBottom {{ type patch; faces ((3 7 6 2) (0 1 5 4)); }}
    frontAndBack {{ type empty; faces ((0 3 2 1) (4 5 6 7)); }}
);
mergePatchPairs ();
""")
        (tmp_dir / "system" / "controlDict").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object controlDict; }
application pisoFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 34.0;
deltaT 0.04; writeControl timeStep; writeInterval 15; purgeWrite 20;
writeFormat ascii; writePrecision 5; writeCompression off; timeFormat general; timePrecision 6;
""")
        (tmp_dir / "system" / "fvSchemes").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default backward; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) Gauss linearUpwind grad(U); div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
""")
        (tmp_dir / "system" / "fvSolution").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object fvSolution; }
solvers { p { solver GAMG; smoother GaussSeidel; tolerance 1e-6; relTol 0.02; } pFinal { $p; relTol 0; } U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-6; relTol 0.05; } }
PISO { nCorrectors 2; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }
""")
        (tmp_dir / "constant" / "transportProperties").write_text(f"""FoamFile
{{ version 2.0; format ascii; class dictionary; object transportProperties; }}
transportModel Newtonian; nu [0 2 -1 0 0 0 0] {nu:.8e};
""")
        (tmp_dir / "constant" / "turbulenceProperties").write_text("""FoamFile
{ version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
""")

        _run_foam(tmp_dir, "blockMesh", timeout=60)

        xs = x_min + (np.arange(nx) + 0.5) * dx
        ys = y_min + (np.arange(ny) + 0.5) * dy
        gx, gy = np.meshgrid(xs, ys)
        if sh == "eureka":
            solid = (np.abs(gx) <= 0.5) & (np.abs(gy) <= 0.5) & ((np.abs(gx) + np.abs(gy)) <= 0.84)
        else:
            solid = (gx * gx + gy * gy) <= (0.5 ** 2)
        fluid_idx = np.flatnonzero(~solid.ravel()).tolist()

        sets_dir = tmp_dir / "constant" / "polyMesh" / "sets"
        sets_dir.mkdir(parents=True, exist_ok=True)
        (sets_dir / "fluidCells").write_text(f"""FoamFile
{{ version 2.0; format ascii; class cellSet; location "constant/polyMesh/sets"; object fluidCells; }}
{len(fluid_idx)}
(
{chr(10).join(str(i) for i in fluid_idx)}
)
""")
        _run_foam(tmp_dir, "subsetMesh fluidCells -patch obstacle -overwrite", timeout=60)
        bfile = tmp_dir / "constant" / "polyMesh" / "boundary"
        bfile.write_text(re.sub(r"(obstacle\s*\{[^}]*?\btype\s+)empty(\s*;)", r"\1wall\2", bfile.read_text(), flags=re.S))

        (tmp_dir / "0").mkdir(parents=True, exist_ok=True)
        u_init = [f"(1 {0.10*math.exp(-0.25*(gx.ravel()[i]-1)**2 - 0.5*gy.ravel()[i]**2):.4f} 0)" for i in fluid_idx]
        (tmp_dir / "0" / "U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField nonuniform List<vector>
{len(u_init)}
(
{chr(10).join(u_init)}
);
boundaryField {{ inlet {{ type fixedValue; value uniform (1 0 0); }} outlet {{ type zeroGradient; }} topBottom {{ type slip; }} obstacle {{ type noSlip; }} frontAndBack {{ type empty; }} }}
""")
        (tmp_dir / "0" / "p").write_text("""FoamFile
{ version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type zeroGradient; } outlet { type fixedValue; value uniform 0; } topBottom { type zeroGradient; } obstacle { type zeroGradient; } frontAndBack { type empty; } }
""")

        _run_foam(tmp_dir, "pisoFoam", timeout=180)

        # Read all saved transient snapshots directly into NumPy snapshot matrix X
        tdirs = []
        for p in tmp_dir.iterdir():
            if p.is_dir():
                try:
                    tv = float(p.name)
                    if tv > 5.0 and (p / "U").is_file():
                        tdirs.append((tv, p))
                except ValueError:
                    pass
        tdirs.sort(key=lambda x: x[0])

        snap_cols = []
        snap_times = []
        for tv, td in tdirs:
            txt = (td / "U").read_text(errors="ignore")
            m = re.search(r"internalField\s+nonuniform\s+List<vector>\s*\d+\s*\((.*?)\)\s*;", txt, re.S)
            if not m:
                continue
            vecs = re.findall(r"\(\s*([\d.eE+-]+)\s+([\d.eE+-]+)\s+[\d.eE+-]+\s*\)", m.group(1))
            if len(vecs) != len(fluid_idx):
                continue
            uy_grid = np.zeros(nx * ny, dtype=np.float64)
            arr_uv = np.array(vecs, dtype=np.float64)
            uy_grid[fluid_idx] = arr_uv[:, 1]
            snap_cols.append(uy_grid)
            snap_times.append(tv)

        X = np.column_stack(snap_cols)  # shape (nx*ny, n_snaps)
        X_mean = np.mean(X, axis=1, keepdims=True)
        X_fluc = X - X_mean
        U_svd, S, Vt = np.linalg.svd(X_fluc, full_matrices=False)
        energy = (S ** 2) / max(np.sum(S ** 2), 1e-12) * 100.0
        cum_energy = np.cumsum(energy)

        fig, axes = plt.subplots(2, 3, figsize=(13.0, 7.6))
        fig.suptitle(
            f"OpenFOAM 卡门涡街瞬态流场 × NumPy SVD (POD) 模态降维分解 (Re={re_val:.0f}, {len(snap_times)} Snapshots)",
            fontsize=13.0,
            fontweight="bold",
            color="#fbbf24",
            y=0.98,
        )

        # Panel 0: Energy spectrum
        ax_e = axes[0, 0]
        k_idx = np.arange(1, len(energy) + 1)
        ax_e.bar(k_idx, energy, color="#38bdf8", alpha=0.85, label="Single Mode %")
        ax_e.plot(k_idx, cum_energy, "o-", color="#fbbf24", ms=4, lw=1.8, label="Cumulative %")
        ax_e.set_title("1. 奇异值能量衰减谱 (SVD Spectrum)")
        ax_e.set_xlabel("POD Mode k")
        ax_e.set_ylabel("Energy Share (%)")
        ax_e.set_ylim(0, 108)
        ax_e.grid(True)
        ax_e.legend(fontsize=8)

        # Panel 1: Temporal mode coefficients Vt[0], Vt[1], Vt[2]
        ax_t = axes[0, 1]
        for m_i, col in ((0, "#f97316"), (1, "#22c55e"), (2, "#a78bfa")):
            if m_i < len(Vt):
                ax_t.plot(snap_times, Vt[m_i] * S[m_i], "o-", ms=3.5, lw=1.8, color=col, label=f"Mode {m_i+1}")
        ax_t.set_title("2. 主模态时间振幅演化 a_k(t)")
        ax_t.set_xlabel("Physical Time t (s)")
        ax_t.set_ylabel("Modal Amplitude")
        ax_t.grid(True)
        ax_t.legend(fontsize=8)

        # Panels 2..5: First 4 Spatial POD Modes (reordered nicely across grid)
        slots = [axes[0, 2], axes[1, 0], axes[1, 1], axes[1, 2]]
        for m_i, axm in enumerate(slots):
            mode_2d = np.ma.masked_where(solid, U_svd[:, m_i].reshape(ny, nx))
            vabs = max(float(np.max(np.abs(mode_2d))), 1e-6)
            axm.imshow(mode_2d, origin="lower", extent=[x_min, x_max, y_min, y_max], cmap="coolwarm", vmin=-vabs, vmax=vabs, aspect="auto")
            axm.set_title(f"POD Mode {m_i+1} ({energy[m_i]:.1f}% Energy)")
            axm.set_xlabel("x / D")
            axm.set_ylabel("y / D")

        plt.tight_layout(rect=[0, 0, 1, 0.94])
        img_b64 = _fig_to_b64(fig)

        df_modes = pd.DataFrame({
            "mode_k": k_idx,
            "singular_value": np.round(S, 4),
            "energy_pct": np.round(energy, 2),
            "cumulative_energy_pct": np.round(cum_energy, 2),
        })
        kpis = {
            "n_snapshots": len(snap_times),
            "grid_points": nx * ny,
            "mode1_energy_pct": round(float(energy[0]), 1),
            "mode12_energy_pct": round(float(cum_energy[1]), 1),
            "top4_energy_pct": round(float(cum_energy[min(3, len(cum_energy) - 1)]), 1),
        }
        code_snippet = """# NumPy SVD 进行流场 POD 本征正交分解
import numpy as np
X_fluc = X - X.mean(axis=1, keepdims=True)       # 去均值脉动场 (N_pts x N_t)
U_pod, S, Vt = np.linalg.svd(X_fluc, full_matrices=False)
energy_pct = (S ** 2) / np.sum(S ** 2) * 100.0   # 各阶涡结构能量占比
X_rank4 = X.mean(1, keepdims=True) + U_pod[:, :4] @ np.diag(S[:4]) @ Vt[:4, :]"""

        return {
            "case_key": key,
            "lab": "pod",
            "params": {"shape": sh, "re": re_val},
            "kpis": kpis,
            "image_b64": img_b64,
            "csv_content": df_modes.to_csv(index=False),
            "table_preview": df_modes.head(10).to_dict(orient="records"),
            "code_snippet": code_snippet,
            "timing_sec": round(time.perf_counter() - t0, 2),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# LAB 4: Pure NumPy Vectorized 2D Navier-Stokes Cavity Solver vs Ghia (1982)
# ==============================================================================

def run_numpy_solver_lab(reynolds: int = 400, grid_n: int = 65) -> Dict[str, Any]:
    t0 = time.perf_counter()
    re_val = min((100, 400, 1000), key=lambda x: abs(x - int(reynolds)))
    N = min((49, 65, 81), key=lambda x: abs(x - int(grid_n)))
    key = hashlib.sha256(f"p2|solver|re={re_val}|n={N}".encode()).hexdigest()[:16]

    h = 1.0 / (N - 1)
    nu = 1.0 / re_val
    dt = min(0.22 * h * h / max(nu, 1e-6), 0.35 * h)
    # Build sparse 2D Laplacian for streamfunction Poisson: -nabla^2 psi = omega
    interior = (N - 2) ** 2
    main_d = np.full(interior, 4.0)
    off_x = np.tile(np.append(np.full(N - 3, -1.0), 0.0), N - 2)[:-1]
    off_y = np.full(interior - (N - 2), -1.0)
    L_mat = sparse.diags([main_d, off_x, off_x, off_y, off_y], [0, -1, 1, -(N - 2), (N - 2)], format="csc")
    solve_poisson = sparse.linalg.factorized(L_mat)

    psi = np.zeros((N, N), dtype=np.float64)
    omega = np.zeros((N, N), dtype=np.float64)
    u = np.zeros((N, N), dtype=np.float64)
    v = np.zeros((N, N), dtype=np.float64)

    # Benchmark naive pure-Python nested loop (10 inner-grid advection+diffusion steps extrapolated)
    t_loop0 = time.perf_counter()
    dummy = np.zeros((N, N))
    for _ in range(10):
        for j in range(1, N - 1):
            for i in range(1, N - 1):
                uc_l, vc_l = u[j, i], v[j, i]
                dwdx_l = (omega[j, i] - omega[j, i - 1]) / h if uc_l >= 0 else (omega[j, i + 1] - omega[j, i]) / h
                dwdy_l = (omega[j, i] - omega[j - 1, i]) / h if vc_l >= 0 else (omega[j + 1, i] - omega[j, i]) / h
                lap_l = (omega[j, i + 1] + omega[j, i - 1] + omega[j + 1, i] + omega[j - 1, i] - 4.0 * omega[j, i]) / (h * h)
                dummy[j, i] = omega[j, i] + dt * (-(uc_l * dwdx_l + vc_l * dwdy_l) + nu * lap_l)
    loop_10_sec = time.perf_counter() - t_loop0

    n_steps = int(min(max(22.0 / max(dt, 1e-5), 2500), 6500))
    t_vec0 = time.perf_counter()
    inv_2h = 1.0 / (2.0 * h)
    inv_h2 = 1.0 / (h * h)
    for _ in range(n_steps):
        rhs = (omega[1:-1, 1:-1] * (h * h)).ravel()
        psi[1:-1, 1:-1] = solve_poisson(rhs).reshape(N - 2, N - 2)

        u[1:-1, 1:-1] = (psi[2:, 1:-1] - psi[:-2, 1:-1]) * inv_2h
        v[1:-1, 1:-1] = -(psi[1:-1, 2:] - psi[1:-1, :-2]) * inv_2h
        u[-1, :] = 1.0

        # Thom's no-slip wall vorticity boundary conditions
        omega[-1, :] = -2.0 * psi[-2, :] * inv_h2 - 2.0 / h
        omega[0, :] = -2.0 * psi[1, :] * inv_h2
        omega[:, 0] = -2.0 * psi[:, 1] * inv_h2
        omega[:, -1] = -2.0 * psi[:, -2] * inv_h2

        # Vectorized upwind advection + central diffusion
        uc, vc = u[1:-1, 1:-1], v[1:-1, 1:-1]
        dwdx = np.where(uc >= 0, (omega[1:-1, 1:-1] - omega[1:-1, :-2]) / h, (omega[1:-1, 2:] - omega[1:-1, 1:-1]) / h)
        dwdy = np.where(vc >= 0, (omega[1:-1, 1:-1] - omega[:-2, 1:-1]) / h, (omega[2:, 1:-1] - omega[1:-1, 1:-1]) / h)
        lap = (omega[1:-1, 2:] + omega[1:-1, :-2] + omega[2:, 1:-1] + omega[:-2, 1:-1] - 4.0 * omega[1:-1, 1:-1]) * inv_h2
        omega[1:-1, 1:-1] += dt * (-(uc * dwdx + vc * dwdy) + nu * lap)
    vec_sec = time.perf_counter() - t_vec0
    est_loop_sec = (loop_10_sec / 10.0) * n_steps
    speedup = est_loop_sec / max(vec_sec, 1e-4)

    ghia_y = [1.0, 0.9766, 0.9688, 0.9609, 0.9531, 0.8516, 0.7344, 0.6172, 0.5, 0.4531, 0.2813, 0.1719, 0.1016, 0.0703, 0.0625, 0.0547, 0.0]
    ghia_u = {
        100: [1.0, 0.8412, 0.7887, 0.7372, 0.6872, 0.2315, 0.0033, -0.1364, -0.2058, -0.2109, -0.1566, -0.1015, -0.0643, -0.0478, -0.0419, -0.0372, 0.0],
        400: [1.0, 0.7584, 0.6844, 0.6176, 0.5589, 0.2909, 0.1626, 0.0214, -0.1148, -0.1712, -0.3273, -0.2430, -0.1461, -0.1034, -0.0927, -0.0819, 0.0],
        1000: [1.0, 0.6593, 0.5749, 0.5112, 0.4660, 0.3330, 0.1872, 0.0570, -0.0608, -0.1065, -0.2781, -0.3829, -0.2973, -0.2222, -0.2020, -0.1811, 0.0],
    }[re_val]

    ys = np.linspace(0.0, 1.0, N)
    xs = np.linspace(0.0, 1.0, N)
    u_mid = u[:, N // 2]
    rmse = float(np.sqrt(np.mean((np.interp(ghia_y, ys, u_mid) - np.array(ghia_u)) ** 2)))

    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2))
    fig.suptitle(
        f"纯 NumPy 矢量化手搓 2D Navier-Stokes 求解器 (Re={re_val}, {N}×{N} 网格)",
        fontsize=13.5,
        fontweight="bold",
        color="#fbbf24",
        y=0.98,
    )

    gx, gy = np.meshgrid(xs, ys)
    umag = np.hypot(u, v)
    axes[0, 0].contourf(gx, gy, umag, levels=28, cmap="turbo")
    axes[0, 0].streamplot(xs, ys, u, v, color="#fff7ed", density=1.35, linewidth=0.9, arrowsize=0.9)
    axes[0, 0].set_title("1. 速度大小云图与二次角涡流线 (NumPy Streamplot)")
    axes[0, 0].set_xlabel("x")
    axes[0, 0].set_ylabel("y")

    vlim = float(np.percentile(np.abs(omega), 97))
    axes[0, 1].contourf(gx, gy, omega, levels=30, cmap="coolwarm", vmin=-vlim, vmax=vlim)
    axes[0, 1].set_title("2. 涡量分布 ω_z (Vorticity Field)")
    axes[0, 1].set_xlabel("x")
    axes[0, 1].set_ylabel("y")

    axes[1, 0].plot(u_mid, ys, color="#38bdf8", lw=2.3, label=f"NumPy Solver ({N}×{N})")
    axes[1, 0].scatter(ghia_u, ghia_y, color="#f97316", s=38, edgecolor="#fff", zorder=5, label="Ghia et al. (1982)")
    axes[1, 0].axvline(0, color="#cbb8a5", ls=":", lw=1)
    axes[1, 0].set_title(f"3. 中轴线 u_x(y) 精度校验 (RMSE = {rmse:.4f})")
    axes[1, 0].set_xlabel("u_x / U_lid")
    axes[1, 0].set_ylabel("y")
    axes[1, 0].grid(True)
    axes[1, 0].legend(fontsize=8.5, framealpha=0.25)

    ax4 = axes[1, 1]
    b4 = ax4.bar(["Pure Python Loop (Est.)", "Vectorized NumPy + Sparse LU"], [est_loop_sec, vec_sec], color=["#fb7185", "#22c55e"])
    for b in b4:
        ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + max(est_loop_sec, vec_sec) * 0.03, f"{b.get_height():.2f}s", ha="center", fontsize=10)
    ax4.set_ylim(0, max(est_loop_sec, vec_sec) * 1.25)
    ax4.set_title(f"4. NumPy 矢量化矩阵加速对比 ({speedup:.1f}× Speedup)")
    ax4.set_ylabel("Solve Time (seconds)")
    ax4.grid(True, axis="y")

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    img_b64 = _fig_to_b64(fig)

    df_out = pd.DataFrame({"y": np.round(ys, 4), "u_x_numpy": np.round(u_mid, 5), "psi_mid": np.round(psi[:, N // 2], 5)})
    kpis = {
        "reynolds": re_val,
        "grid": f"{N}×{N}",
        "n_steps": n_steps,
        "vec_solve_sec": round(vec_sec, 2),
        "loop_est_sec": round(est_loop_sec, 1),
        "speedup_x": round(speedup, 1),
        "ghia_rmse": round(rmse, 4),
    }
    code_snippet = """# NumPy 切片矢量化 Navier-Stokes 离散（比 Python for 循环快几十倍）
dwdx = np.where(uc >= 0, (w[1:-1,1:-1]-w[1:-1,:-2])/h, (w[1:-1,2:]-w[1:-1,1:-1])/h)
dwdy = np.where(vc >= 0, (w[1:-1,1:-1]-w[:-2,1:-1])/h, (w[2:,1:-1]-w[1:-1,1:-1])/h)
lap  = (w[1:-1,2:] + w[1:-1,:-2] + w[2:,1:-1] + w[:-2,1:-1] - 4*w[1:-1,1:-1]) / (h*h)
w[1:-1,1:-1] += dt * (-(uc*dwdx + vc*dwdy) + nu * lap)"""

    return {
        "case_key": key,
        "lab": "solver",
        "params": {"re": re_val, "grid_n": N},
        "kpis": kpis,
        "image_b64": img_b64,
        "csv_content": df_out.to_csv(index=False),
        "table_preview": df_out.iloc[:: max(1, N // 10)].to_dict(orient="records"),
        "code_snippet": code_snippet,
        "timing_sec": round(time.perf_counter() - t0, 2),
    }


# ==============================================================================
# LAB 5: Pandas Regex Data-Cleaning Lab (Melbourne Coles vs Woolworths)
# ==============================================================================

def run_deals_pandas_lab(store: str = "ALL", min_discount_pct: float = 0.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    st_f = store if store in ("Coles", "Woolworths") else "ALL"
    min_d = float(min_discount_pct)
    key = hashlib.sha256(f"p2|deals|{st_f}|{min_d:.0f}".encode()).hexdigest()[:16]

    snap = _fetch_json("https://coles-wws-deals-worker.ibalamayaka.workers.dev/api/latest")
    raw_items = snap.get("coles", []) + snap.get("woolworths", [])
    df = pd.DataFrame(raw_items)
    if df.empty:
        raise RuntimeError("No active grocery deals returned from API")

    def extract_econ(row):
        txt = f"{row.get('title', '')} {row.get('summary', '')}"
        pairs = re.findall(r"\$(\d+(?:\.\d+)?)\s*off\s*(?:with\s*)?(?:\$|a\s*\$)(\d+(?:\.\d+)?)", txt, flags=re.I)
        best_off, best_spend, best_pct = np.nan, np.nan, np.nan
        for o_s, s_s in pairs:
            o, s = float(o_s), float(s_s)
            if o > 0 and s >= o:
                pct = round((o / s) * 100.0, 1)
                if np.isnan(best_pct) or pct > best_pct:
                    best_off, best_spend, best_pct = o, s, pct
        if np.isnan(best_pct):
            pm = re.search(r"(\d+(?:\.\d+)?)\s*%\s*off|half\s*price", txt, flags=re.I)
            if pm:
                best_pct = 50.0 if "half" in pm.group(0).lower() else float(pm.group(1))
        cat = "Half-Price / %" if (not np.isnan(best_pct) and best_pct >= 45) else (
            "Coupon Spend&Save" if row.get("coupon") else (
                "Auto Spend&Save" if not np.isnan(best_off) else "Free Gift / Other"
            )
        )
        return pd.Series([best_off, best_spend, best_pct, cat], index=["off_aud", "min_spend_aud", "discount_pct", "category"])

    df[["off_aud", "min_spend_aud", "discount_pct", "category"]] = df.apply(extract_econ, axis=1)
    df["expiry_clean"] = df["expiry"].astype(str).str.slice(0, 10)
    if st_f != "ALL":
        df = df[df["store"] == st_f]
    if min_d > 0:
        df = df[df["discount_pct"].fillna(0) >= min_d]
    df = df.sort_values(["discount_pct", "off_aud"], ascending=[False, False]).reset_index(drop=True)

    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2))
    fig.suptitle(
        f"Pandas 正则脏数据清洗实战：Coles vs Woolworths 墨尔本每周折扣 ({snap.get('generatedAt', '')})",
        fontsize=13.0,
        fontweight="bold",
        color="#fbbf24",
        y=0.98,
    )

    ax1 = axes[0, 0]
    top_pct = df.dropna(subset=["discount_pct"]).head(7).iloc[::-1]
    if not top_pct.empty:
        lbls = [f"[{r['store'][:4]}] {r['coupon'] or r['title'][:18]}" for _, r in top_pct.iterrows()]
        cols = ["#e01a22" if s == "Coles" else "#22c55e" for s in top_pct["store"]]
        bars = ax1.barh(lbls, top_pct["discount_pct"], color=cols)
        for b in bars:
            ax1.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2, f"{b.get_width():.0f}%", va="center", fontsize=9)
        ax1.set_xlim(0, max(top_pct["discount_pct"].max() * 1.18, 25))
    ax1.set_title("1. 正则解析等效折扣率排行榜 (%)")
    ax1.set_xlabel("Equivalent Discount (%)")
    ax1.grid(True, axis="x")

    ax2 = axes[0, 1]
    sp_df = df.dropna(subset=["min_spend_aud", "off_aud"])
    if not sp_df.empty:
        for sname, col in (("Coles", "#e01a22"), ("Woolworths", "#22c55e")):
            sub = sp_df[sp_df["store"] == sname]
            if not sub.empty:
                ax2.scatter(sub["min_spend_aud"], sub["off_aud"], color=col, s=85, edgecolor="#fff", label=sname)
                for _, r in sub.iterrows():
                    ax2.annotate(r["coupon"] or f"${int(r['off_aud'])}", (r["min_spend_aud"], r["off_aud"] + 0.8), fontsize=8.5, ha="center")
    ax2.set_title("2. 消费门槛 vs 立减金额散点图 (Spend & Save)")
    ax2.set_xlabel("Minimum Spend Threshold (AUD)")
    ax2.set_ylabel("Cash Off (AUD)")
    ax2.grid(True)
    ax2.legend(fontsize=8.5, framealpha=0.25)

    ax3 = axes[1, 0]
    piv = df.groupby(["store", "category"]).size().unstack(fill_value=0)
    if not piv.empty:
        piv.plot(kind="bar", stacked=True, ax=ax3, colormap="Set2", rot=0)
    ax3.set_title("3. 超市 × 优惠类型交叉分组统计 (GroupBy + Unstack)")
    ax3.set_xlabel("Supermarket")
    ax3.set_ylabel("Number of Active Deals")
    ax3.grid(True, axis="y")

    ax4 = axes[1, 1]
    ax4.axis("off")
    ax4.text(0.05, 0.86, "4. 本周清洗后周末推荐攻略", fontsize=12.5, fontweight="bold", color="#fbbf24")
    picks = [
        f"共清洗有效优惠: {len(df)} 条（Coles {int((df['store']=='Coles').sum())} · WWS {int((df['store']=='Woolworths').sum())}）",
        f"平均可解析折扣率: {df['discount_pct'].mean():.1f}%" if df["discount_pct"].notna().any() else "平均可解析折扣率: N/A",
        f"最高单笔立减金额: A${df['off_aud'].max():.0f}" if df["off_aud"].notna().any() else "最高单笔立减: 半价单品",
        f"可用优惠码总数: {int(df['coupon'].astype(str).str.len().gt(0).sum())} 个",
    ]
    for idx, p in enumerate(picks):
        ax4.text(0.07, 0.70 - idx * 0.12, f"•  {p}", fontsize=10.5)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    img_b64 = _fig_to_b64(fig)

    clean_cols = ["store", "coupon", "off_aud", "min_spend_aud", "discount_pct", "category", "expiry_clean", "title"]
    code_snippet = """# Pandas 正则清洗澳洲超市杂乱优惠文本
import pandas as pd
df = pd.read_csv("https://powerbi-portfolio-cloud.ibalamayaka.workers.dev/api/export/deals.csv")
# 使用正则表达式批量抽出满减门槛与折扣百分比
nums = df["title"].str.extract(r"\\$(\\d+)\\s*off.*\\$(\\d+)")
df["off_aud"], df["min_spend"] = nums[0].astype(float), nums[1].astype(float)
df["pct"] = (df["off_aud"] / df["min_spend"] * 100).round(1)
df.groupby("store")[["off_aud", "pct"]].agg(["count", "mean", "max"])"""

    return {
        "case_key": key,
        "lab": "deals",
        "params": {"store": st_f, "min_discount_pct": min_d},
        "kpis": {
            "total_cleaned": int(len(df)),
            "best_pct": round(float(df["discount_pct"].max()), 1) if df["discount_pct"].notna().any() else 0.0,
            "avg_pct": round(float(df["discount_pct"].mean()), 1) if df["discount_pct"].notna().any() else 0.0,
            "coupon_count": int(df["coupon"].astype(str).str.len().gt(0).sum()),
        },
        "image_b64": img_b64,
        "csv_content": df[clean_cols].to_csv(index=False),
        "table_preview": df[clean_cols].fillna("").head(12).to_dict(orient="records"),
        "code_snippet": code_snippet,
        "timing_sec": round(time.perf_counter() - t0, 2),
    }
