export type Role = "doctor" | "coordinator" | "editor";
export type View =
  | "Today"
  | "Calendar"
  | "Tasks"
  | "Messages"
  | "Content"
  | "Team"
  | "Memory"
  | "Sources"
  | "Reports";
export type OfficeRecord = {
  id: string;
  version: number;
  kind?: string;
  [key: string]: unknown;
};
export type Source = OfficeRecord & {
  title: string;
  url: string;
  excerpt: string;
  accessed_at: string;
  provenance: string;
};
export type Snapshot = {
  workspace_id: string;
  role: Role;
  clock: string;
  doctor_name: string;
  events: OfficeRecord[];
  tasks: OfficeRecord[];
  messages: OfficeRecord[];
  patient_admin: OfficeRecord[];
  content: OfficeRecord[];
  engineering: OfficeRecord[];
  reports: OfficeRecord[];
  preferences: OfficeRecord[];
  sources: Source[];
  stats: {
    open_tasks: number;
    needs_attention: number;
    content_in_review: number;
    [key: string]: unknown;
  };
};
export type Action = {
  id: string;
  kind: string;
  status: string;
  payload: Record<string, unknown>;
  receipt?: unknown;
  error?: string;
};
export type Plan = {
  id: string;
  run_id?: string;
  status: string;
  summary: string;
  actions: Action[];
  expires_at?: string;
};
export type Step = {
  id: string;
  kind: string;
  title: string;
  detail?: unknown;
  status: string;
  duration_ms?: number;
  model?: string;
  tokens?: number;
  cost?: number;
};
export type Run = {
  id: string;
  message: string;
  status: string;
  answer?: string;
  plan?: Plan;
  plan_id?: string;
  steps?: Step[];
  usage?: { tokens?: number; cost?: number; latency_ms?: number };
  error?: string;
  created_at?: string;
};
