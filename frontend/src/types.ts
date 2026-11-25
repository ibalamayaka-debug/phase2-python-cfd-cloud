export type LabId = 'report' | 'vehicle' | 'pod' | 'solver' | 'deals';

export interface LabSummary {
  case_key: string;
  lab: LabId;
  params: Record<string, any>;
  kpis: Record<string, any>;
  timing_sec: number;
}

export interface LabPayload {
  case_key: string;
  lab: LabId;
  params: Record<string, any>;
  kpis: Record<string, any>;
  image_b64: string;
  csv_content: string;
  table_preview: Array<Record<string, any>>;
  code_snippet: string;
  timing_sec: number;
}

export interface LabResponse {
  status: string;
  cached: boolean;
  backend: string;
  lab: LabId;
  case_key: string;
  result: LabPayload;
  urls: {
    json: string;
    png: string;
    csv: string;
  };
}
