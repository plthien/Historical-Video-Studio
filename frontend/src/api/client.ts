/** Typed transport for the A1-owned local API. Never mark future-owner routes as successful. */
export type GateId = "G1" | "G2" | "G3" | "G4" | "G5";
export type GateState = "DRAFT" | "PREPARING" | "READY_FOR_REVIEW" | "APPROVED" |
  "CHANGES_REQUESTED" | "BLOCKED" | "REJECTED" | "STALE";
export interface ApiProblem {
  code: string; message: string; remediation: string; retryable: boolean;
  entity_id: string | null; blocking_gate: GateId | null;
}
export interface Gate {
  gate_id: GateId; state: GateState; candidate_sha256: string | null;
  dependency_fingerprint: string | null; blockers: string[]; revision: number;
}
export interface ProjectInfo { project_id: string; project_revision: number; gates: Gate[]; }
export interface StoryPayload {
  project: {project_id: string; title: string};
  sections: {section_id: string; narration: string; claim_refs: string[]}[];
  claims: {claim_id: string; text: string; critical: boolean; status: string;
           source_leads: {url: string; title?: string}[]}[];
}
export interface StoryView {
  project_revision: number; candidate_sha256: string; story: StoryPayload;
  claim_reviews: {claim_id: string; status: string; evidence_note: string; source_url?: string}[];
}
export interface JobInfo {
  job_id: string; kind: string; state: string; error_code: string | null;
  provider_task_id: string | null; cancel_requested: number; retry_count: number;
}
export interface ProjectCreated { project_id: string; project_revision: number; next_action: string; }
export interface GateDecision {
  decision: "APPROVED" | "CHANGES_REQUESTED" | "REJECTED";
  candidate_sha256: string; dependency_fingerprint: string;
  expected_revision: number; affected_ids: string[]; comment: string;
}
export class ApiError extends Error {
  constructor(public status: number, public problem: ApiProblem) {
    super(problem.message);
  }
}
export const origin = import.meta.env.VITE_API_ORIGIN ?? "http://127.0.0.1:8000/api/v1";
export async function request<T>(path: string, method = "GET", payload?: unknown, idempotencyKey?: string,
                                 signal?: AbortSignal): Promise<T> {
  const response = await fetch(origin + path, {
    signal,
    method, headers: {
      ...(payload === undefined ? {} : {"Content-Type": "application/json"}),
      ...(idempotencyKey === undefined ? {} : {"Idempotency-Key": idempotencyKey})
    }, body: payload === undefined ? undefined : JSON.stringify(payload)
  });
  const body = await response.json();
  if (!response.ok) throw new ApiError(response.status, body as ApiProblem);
  return body as T;
}
const safe = encodeURIComponent;
export const api = {
  createProject(title: string) {
    return request<ProjectCreated>("/projects", "POST", {
      title, language: "en", style_id: "HistoryEditorialPaper.v1"
    });
  },
  project(id: string) { return request<ProjectInfo>(`/projects/${safe(id)}`); },
  gates(id: string) { return request<Gate[]>(`/projects/${safe(id)}/gates`); },
  story(id: string) { return request<StoryView>(`/projects/${safe(id)}/story`); },
  jobs(id: string) { return request<JobInfo[]>(`/projects/${safe(id)}/jobs`); },
  cancelJob(id: string, key: string) {
    return request<JobInfo>(`/jobs/${safe(id)}/cancel`, "POST", undefined, key);
  },
  cancelManaged(projectId:string, jobId:string,key:string) {
    return request<JobInfo>(`/projects/${safe(projectId)}/jobs/${safe(jobId)}/cancel`,
      "POST",undefined,key);
  },
  retryManaged(projectId:string, jobId:string,key:string) {
    return request<JobInfo>(`/projects/${safe(projectId)}/jobs/${safe(jobId)}/retry`,
      "POST",undefined,key);
  },
  async importStory(id: string, story: unknown, revision: number, key: string) {
    return request<{project_revision: number; candidate_sha256: string}>(
      `/projects/${safe(id)}/story/import?expected_revision=${revision}`, "POST", story, key);
  },
  reviewClaim(id: string, claim: string, expected_revision: number, status: "REVIEWED" | "VERIFIED",
              evidence_note: string, key: string, source_url: string | null = null) {
    return request<{project_revision: number}>(
      `/projects/${safe(id)}/story/claims/${safe(claim)}/review`,
      "POST", {status, evidence_note, source_url, expected_revision}, key);
  },
  decide(id: string, gate: GateId, decision: GateDecision, key: string) {
    return request<{approval_id: string; project_revision: number; state: string; job_id?: string}>(
      `/projects/${safe(id)}/gates/${gate}/decision`, "POST", decision, key);
  }
};
