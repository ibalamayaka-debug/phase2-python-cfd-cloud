"""
Modal Serverless Python + OpenFOAM v2512 Cloud Compute App for Phase 2 Curriculum (5-in-1):
  1. /run/report  : OpenFOAM auto-report (Convergence + Pressure curve + Velocity profile)
  2. /run/vehicle : 3-Car Pandas & NumPy Aero Regression + Annual Cost Comparison
  3. /run/pod     : Transient OpenFOAM pisoFoam Wake + NumPy SVD POD Modal Decomposition
  4. /run/solver  : Pure NumPy Vectorized 2D Navier-Stokes Cavity Solver vs Ghia (1982)
  5. /run/deals   : Live Melbourne Coles vs Woolworths Pandas Regex Cleaning & Strategy
"""

import os

import modal

app = modal.App("phase2-python-cfd-modal")

image = (
    modal.Image.from_registry("opencfd/openfoam-run:2512", add_python="3.11")
    .apt_install("libglu1-mesa", "libgl1", "libgomp1", "fonts-wqy-microhei")
    .pip_install("numpy", "pandas", "matplotlib", "scipy", "vtk", "fastapi[standard]")
    .add_local_file("compute/phase2_labs.py", "/app/phase2_labs.py")
)


@app.function(
    image=image,
    cpu=4.0,
    memory=4096,
    timeout=300,
    scaledown_window=30,
    secrets=[modal.Secret.from_name("phase2-lab-secrets")],
)
@modal.asgi_app()
def fastapi_app():
    import sys

    sys.path.insert(0, "/app")
    from fastapi import Body, FastAPI, Header, HTTPException
    from phase2_labs import (
        run_deals_pandas_lab,
        run_numpy_solver_lab,
        run_openfoam_report_lab,
        run_pod_svd_lab,
        run_vehicle_analytics_lab,
    )

    web_app = FastAPI(title="Phase 2 Python + Simulation Cloud Engine (5-in-1)")

    def _auth(authorization: str | None):
        expected = os.environ.get("COMPUTE_AUTH_TOKEN", "")
        if expected and (not authorization or authorization != f"Bearer {expected}"):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @web_app.get("/health")
    def health():
        return {"status": "ok", "labs": ["report", "vehicle", "pod", "solver", "deals"]}

    @web_app.post("/run/report")
    def api_report(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _auth(authorization)
        try:
            return run_openfoam_report_lab(
                case_type=str(payload.get("case_type", "step")),
                re_or_u=float(payload.get("re_or_u", 37500.0)),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @web_app.post("/run/vehicle")
    def api_vehicle(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _auth(authorization)
        try:
            return run_vehicle_analytics_lab(
                annual_km=float(payload.get("annual_km", 20000.0)),
                elec_price=float(payload.get("elec_price", 0.30)),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @web_app.post("/run/pod")
    def api_pod(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _auth(authorization)
        try:
            return run_pod_svd_lab(
                shape=str(payload.get("shape", "cylinder")),
                reynolds=float(payload.get("re", 150.0)),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @web_app.post("/run/solver")
    def api_solver(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _auth(authorization)
        try:
            return run_numpy_solver_lab(
                reynolds=int(payload.get("re", 400)),
                grid_n=int(payload.get("grid_n", 65)),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @web_app.post("/run/deals")
    def api_deals(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _auth(authorization)
        try:
            return run_deals_pandas_lab(
                store=str(payload.get("store", "ALL")),
                min_discount_pct=float(payload.get("min_discount_pct", 0.0)),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return web_app
