import { bindings, defineConfig } from "cf/config";
import * as entrypoint from "./worker/src/index.ts" with { type: "cf-worker" };

export default defineConfig({
  worker: {
    name: "phase2-python-cfd-cloud",
    compatibilityDate: "2026-11-17",
    entrypoint,
    assets: {
      notFoundHandling: "single-page-application",
      runWorkerFirst: ["/api/*"],
    },
    env: {
      PHASE2_LAB_KV: bindings.kv({ id: "c840b0df4fb14b6bb1c8ffbd7ae84498" }),
      RATE_LIMIT_KV: bindings.kv({ id: "881e01edca014d0c8236b3c61688a937" }),
      COMPUTE_BASE_URL: bindings.text(
        "https://ibalamayaka-debug--phase2-python-cfd-modal-fastapi-app.us-east.modal.run"
      ),
      COMPUTE_AUTH_TOKEN: bindings.secret(),
      ALLOWED_ORIGIN: bindings.text("*"),
      MAX_RUNS_PER_IP_PER_HOUR: bindings.text("30"),
      ASSETS: bindings.assets(),
    },
  },
});
