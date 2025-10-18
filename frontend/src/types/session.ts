export interface FileEntry {
  id: string;
  file: File;
}

export interface Requirement {
  id: string | number;
  naslov?: string;
  besedilo?: string;
  clen?: string;
  skupina?: string;
  kategorija?: string;
  status?: string;
}

export interface RequirementResult {
  id: string;
  status?: string;
  obrazlozitev?: string;
  predlagani_ukrep?: string;
  [key: string]: unknown;
}

export interface SavedSessionRecord {
  session_id: string;
  project_name: string;
  summary?: string;
  updated_at?: string;
  source?: 'local' | 'remote';
}

export interface StatusMessage {
  type: 'info' | 'success' | 'error';
  message: string;
}

export interface RequirementRevisionMap {
  [requirementId: string]: string[];
}

export interface AnalysisResultPayload {
  results_map?: Record<string, RequirementResult>;
  zahteve?: Requirement[];
  requirement_revisions?: RequirementRevisionMap;
}
