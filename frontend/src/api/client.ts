import type {
  AnalysisReport,
  AuditLog,
  Behaviour,
  ComplianceMatrix,
  CounterfactualResult,
  Decision,
  Finding,
  FindingSummary,
  GraphView,
  Health,
  RelationshipPath,
  Robustness,
  Rulebook,
  Similarity,
  SimilarityDetail,
  Snapshot,
  Tender,
  Verification,
  RestructuringPlan,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies set their own multipart boundary; everything else is JSON.
  const json = !(init?.body instanceof FormData);
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(json ? { "Content-Type": "application/json" } : {}), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export interface UploadTenderInput {
  file: File;
  title?: string;
  department?: string;
  bid_deadline?: string;
}

const form = (fields: Record<string, string | Blob | undefined>) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== "") fd.append(k, v);
  return fd;
};

const upload = <T>(path: string, body: FormData, method = "POST") => request<T>(path, { method, body });

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  tenders: () => request<Tender[]>("/api/tenders"),
  uploadTender: ({ file, ...meta }: UploadTenderInput) =>
    upload<{ tender_id: string; title: string }>("/api/uploads/tender", form({ file, ...meta })),
  uploadTenderDocument: (tid: string, file: File, kind: "tender_annex" | "scope" | "specification") =>
    upload<{ document_id: string }>(`/api/tenders/${tid}/documents`, form({ file, kind })),
  uploadBoq: (tid: string, file: File) =>
    upload<{ rows: number; total_amount_inr_cr: number | null }>(`/api/tenders/${tid}/boq`, form({ file })),
  uploadBiddersCsv: (tid: string, file: File) => upload<{ added: number }>(`/api/uploads/${tid}/bidders.csv`, form({ file })),
  restructure: (tid: string, weights: Record<string, number> = {}) =>
    post<RestructuringPlan>(`/api/tenders/${tid}/restructure`, { weights }),
  restructuring: (tid: string) => request<RestructuringPlan>(`/api/tenders/${tid}/restructuring`),
  restructuringDossier: (tid: string) => post<{ url: string }>(`/api/tenders/${tid}/restructuring/dossier`),
  restructuringDossierUrl: (tid: string) => `${BASE}/api/tenders/${tid}/restructuring/dossier.pdf`,
  marketStatus: () => request<{ real_data_loaded: boolean; sources: { source_id: string }[]; counts: Record<string, number>; hint?: string }>("/api/market/status"),
  tamper: (documentId?: string) => post<{ document_id: string; filename: string; change: string }>(
    "/api/demo/tamper",
    { document_id: documentId ?? null },
  ),
  restore: () => post<{ restored: string[] }>("/api/demo/restore"),

  tender: (tid: string) => request<Tender>(`/api/tenders/${tid}`),
  analyze: (tid: string) => post<AnalysisReport>(`/api/tenders/${tid}/analyze`, {}),
  rules: (tid: string) => request<Rulebook>(`/api/tenders/${tid}/rules`),
  compliance: (tid: string) => request<ComplianceMatrix>(`/api/tenders/${tid}/compliance`),
  graph: (tid: string) => request<GraphView>(`/api/tenders/${tid}/graph`),
  vendorGraph: (tid: string, vid: string, depth = 1) =>
    request<GraphView>(`/api/tenders/${tid}/graph/vendors/${vid}?depth=${depth}`),
  paths: (tid: string, a: string, b: string) =>
    request<{ paths: RelationshipPath[] }>(`/api/tenders/${tid}/graph/paths?a=${a}&b=${b}&include_tenders=true`),
  similarity: (tid: string) => request<Similarity>(`/api/tenders/${tid}/similarity`),
  similarityPair: (tid: string, a: string, b: string) =>
    request<SimilarityDetail>(`/api/tenders/${tid}/similarity/${a}/${b}`),
  behaviour: (tid: string) => request<Behaviour>(`/api/tenders/${tid}/behaviour`),

  findings: (tid: string) => request<FindingSummary[]>(`/api/tenders/${tid}/findings`),
  finding: (fid: string) => request<Finding>(`/api/findings/${fid}`),
  robustness: (fid: string) => request<Robustness>(`/api/findings/${fid}/robustness`),
  counterfactual: (fid: string, remove: string[], record = true) =>
    post<CounterfactualResult>(`/api/findings/${fid}/counterfactual`, { remove, record, actor: "auditor" }),
  disposition: (fid: string, decision: Decision, auditor: string, notes: string) =>
    post<{ status: string }>(`/api/findings/${fid}/disposition`, { decision, auditor, notes }),
  auditLog: (tid: string) => request<AuditLog>(`/api/tenders/${tid}/audit-log`),

  snapshots: (tid: string) => request<Snapshot[]>(`/api/tenders/${tid}/evidence/snapshots`),
  snapshot: (sid: string) => request<Snapshot>(`/api/evidence/snapshots/${sid}`),
  finalize: (tid: string, auditor: string, note = "") =>
    post<Snapshot>(`/api/tenders/${tid}/evidence/finalize`, { auditor, note }),
  verify: (sid: string) => request<Verification>(`/api/evidence/snapshots/${sid}/verify`),
  dossierUrl: (tid: string) => `${BASE}/api/tenders/${tid}/dossier-data`,
  documentUrl: (docId: string, page?: number | null) =>
    `${BASE}/api/documents/${docId}/file${page ? `#page=${page}` : ""}`,
};
