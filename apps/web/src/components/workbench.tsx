"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import ReactMarkdown from "react-markdown";
import {
  ArrowRight,
  ArrowUp,
  AudioLines,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleCheck,
  Clock3,
  Code2,
  Download,
  ExternalLink,
  FileText,
  History,
  Inbox,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  Menu,
  Mic,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
  Users,
  Volume2,
  X,
} from "lucide-react";
import type {
  Action,
  OfficeRecord,
  Role,
  Run,
  Snapshot,
  Source,
  View,
} from "@/lib/types";
import { recordingToWav } from "@/lib/audio";

const NAV: { name: View; icon: typeof Sun }[] = [
  { name: "Today", icon: Sun },
  { name: "Calendar", icon: CalendarDays },
  { name: "Tasks", icon: ListChecks },
  { name: "Messages", icon: Inbox },
  { name: "Content", icon: FileText },
  { name: "Team", icon: Users },
  { name: "Memory", icon: BookOpen },
  { name: "Sources", icon: Search },
  { name: "Reports", icon: LayoutDashboard },
];
const ROLE_LABELS: Record<Role, string> = {
  doctor: "Doctor",
  coordinator: "Coordinator",
  editor: "Content editor",
};
const STARTERS = [
  {
    icon: ListChecks,
    title: "Prepare tomorrow",
    text: "Catch the details before the day starts.",
    request:
      "Prepare tomorrow, protect my clinic time, and handle useful follow-up. Check schedules, paperwork, messages and open tasks, explain deadlines, and use existing tasks where possible. Show me any changes before applying them.",
  },
  {
    icon: CalendarDays,
    title: "Make room for the team",
    text: "Protect clinic time. Move decisions forward.",
    request:
      "Protect my clinic time and prepare an engineering update. Check my preferences, the schedule and team updates, then propose a suitable time for the engineering meeting and any needed follow-up tasks.",
  },
  {
    icon: FileText,
    title: "Develop a content idea",
    text: "Turn a thought into work ready for review.",
    request:
      "Create a short video about why scar consultation pricing is individual. Use the public source material, prepare a script and caption for review, assign the content editor a production task, and propose a recording time that fits the schedule.",
  },
];
const SCENARIOS = [
  {
    value: "paperwork_complete",
    label: "Paperwork arrives",
    description:
      "Complete the missing paperwork and reconcile linked follow-up tasks.",
  },
  {
    value: "occupy_proposed_slot",
    label: "Availability changes",
    description:
      "Add a conflict to the proposed meeting time before you approve it.",
  },
  {
    value: "task_timeout_after_write",
    label: "Interrupt after a saved action",
    description:
      "The next task write succeeds, then times out. Resume without a duplicate.",
  },
  {
    value: "reset_failure",
    label: "Clear the interruption",
    description:
      "Remove the test interruption so unfinished work can continue.",
  },
  {
    value: "content_reviewed",
    label: "Content review completes",
    description:
      "Approve the demonstration draft and reconcile its review task.",
  },
];

function value(record: OfficeRecord, field: string): string {
  const v = record[field];
  return typeof v === "string"
    ? v
    : v === null || v === undefined
      ? ""
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
}
function label(text: string) {
  return text
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function when(
  raw: unknown,
  options: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit" },
) {
  if (!raw || Number.isNaN(new Date(String(raw)).getTime()))
    return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    ...options,
    timeZone: "America/Los_Angeles",
  }).format(new Date(String(raw)));
}
function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
class RequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
function money(value?: number) {
  return value === undefined || value === null
    ? "Not reported"
    : `$${Number(value).toFixed(4)}`;
}
function isActive(run?: Run | null) {
  return Boolean(run && ["queued", "running"].includes(run.status));
}
function friendlyStatus(status = "") {
  return (
    (
      {
        awaiting_approval: "Your approval needed",
        running: "Working",
        queued: "Queued",
        completed: "Complete",
        failed: "Needs attention",
        partial: "Partly complete",
        cancelled: "Cancelled",
        pending: "Awaiting approval",
        in_review: "In review",
        stale: "Availability changed",
      } as Record<string, string>
    )[status] || label(status)
  );
}
function Status({ status }: { status: string }) {
  return (
    <span className={`status status-${status}`}>
      {["completed", "complete", "approved"].includes(status) && (
        <Check size={11} />
      )}
      {friendlyStatus(status)}
    </span>
  );
}
function Empty({
  title,
  text,
  icon: Icon = Inbox,
}: {
  title: string;
  text: string;
  icon?: typeof Inbox;
}) {
  return (
    <div className="empty">
      <Icon size={25} strokeWidth={1.3} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function SourceLink({ source }: { source: Source }) {
  return (
    <a
      className="source-link"
      href={source.url}
      target="_blank"
      rel="noreferrer"
    >
      <BookOpen size={13} />
      <span>{source.title}</span>
      <ExternalLink size={12} />
    </a>
  );
}
function SourceCheck({ source }: { source: Source }) {
  const check =
    source.live_check ||
    (source.data && typeof source.data === "object"
      ? (source.data as Record<string, unknown>).live_check
      : null);
  if (!check || typeof check !== "object") return null;
  const result = check as Record<string, unknown>;
  return (
    <div className="source-check-result">
      <span
        className={`status ${result.status === "reachable" ? "status-completed" : "status-failed"}`}
      >
        {result.status === "reachable" ? "Page reachable" : "Page unavailable"}
      </span>
      <span>
        Checked{" "}
        {when(result.checked_at, {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })}
      </span>
      {result.changed === true && (
        <strong>Page content has changed since the saved version.</strong>
      )}
      {typeof result.note === "string" && <p>{result.note}</p>}
    </div>
  );
}
function renderValue(value: unknown): string {
  return typeof value === "string"
    ? value
    : value === null || value === undefined
      ? "—"
      : typeof value === "object"
        ? JSON.stringify(value, null, 2)
        : String(value);
}
function actionValue(key: string, value: unknown, snapshot: Snapshot): string {
  if (key === "review_task" && value && typeof value === "object") {
    const task = value as Record<string, unknown>;
    return [
      task.title ? String(task.title) : "Review this content",
      task.owner ? `Assigned to ${String(task.owner)}` : null,
      task.due_at
        ? `Due ${when(task.due_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
        : null,
      task.follow_up_permission
        ? "Close this review task when the content is marked reviewed."
        : null,
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (["start", "end", "due_at"].includes(key))
    return when(value, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  if (key === "follow_up_permission")
    return "When the linked work is confirmed complete, close this follow-up task automatically.";
  if (key === "auto_close_on_paperwork")
    return value
      ? "Close when the paperwork is received"
      : "Keep open until reviewed";
  if (key === "access_scope")
    return value === "office"
      ? "Office team"
      : value === "content"
        ? "Content team"
        : label(String(value));
  if (key === "key") return label(String(value));
  if (key.endsWith("_id") && typeof value === "string") {
    const record = [
      ...snapshot.events,
      ...snapshot.patient_admin,
      ...snapshot.tasks,
      ...snapshot.content,
    ].find((item) => item.id === value);
    return record
      ? String(record.title || record.patient_name || value)
      : value;
  }
  if (key === "source_ids" && Array.isArray(value))
    return value
      .map(
        (id) =>
          snapshot.sources.find((source) => source.id === id)?.title ||
          String(id),
      )
      .join("; ");
  if (key === "workflow" || key === "scope" || key === "status")
    return label(String(value));
  return renderValue(value);
}
function actionLabel(key: string) {
  return (
    (
      {
        related_record_id: "Related work",
        event_id: "Meeting",
        content_id: "Content",
        source_ids: "Supporting sources",
        access_scope: "Visible to",
        follow_up_permission: "Follow-through permission",
        auto_close_on_paperwork: "When paperwork arrives",
        workflow: "Purpose",
        key: "Preference",
        due_at: "Due",
        start: "Start time",
        end: "End time",
      } as Record<string, string>
    )[key] || label(key)
  );
}
function actionName(action: Action) {
  return (
    (
      {
        move_meeting: "Move internal meeting",
        create_task: "Assign a task",
        deliver_demo_message: "Deliver a demonstration message",
        save_preference: "Remember a preference",
        create_content: "Prepare content",
        create_recording: "Reserve recording time",
        save_report: "Save a report",
      } as Record<string, string>
    )[action.kind] || label(action.kind)
  );
}

const serverUnavailableMessage =
  "The demo server is still unavailable. Your saved work is safe. Please retry the connection in a moment.";

export default function Workbench() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [view, setView] = useState<View>("Today");
  const [role, setRole] = useState<Role>("doctor");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showInspector, setShowInspector] = useState(false);
  const [showControls, setShowControls] = useState(false);
  const [showMobileNav, setShowMobileNav] = useState(false);
  const [taskFilter, setTaskFilter] = useState("all");
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [query, setQuery] = useState("");
  const [editingPreference, setEditingPreference] = useState<string | null>(
    null,
  );
  const [preferenceDraft, setPreferenceDraft] = useState("");
  const [expandedMessage, setExpandedMessage] = useState<string | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [connection, setConnection] = useState("Connecting");
  const [localIdentity, setLocalIdentity] = useState(false);
  const [exportLink, setExportLink] = useState("");
  const [serverStarting, setServerStarting] = useState(false);
  const [serverUnavailable, setServerUnavailable] = useState(false);
  const readyAt = useRef(0);
  const readiness = useRef<Promise<void> | null>(null);
  const client = useRef<SupabaseClient | null>(null);
  const developmentToken = useRef("");
  const workspace = useRef("");
  const currentRole = useRef<Role>("doctor");
  const initialized = useRef(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const microphone = useRef<MediaStream | null>(null);
  const recordingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioPlayer = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef("");
  const composer = useRef<HTMLTextAreaElement | null>(null);

  const ensureReady = useCallback((force = false): Promise<void> => {
    if (!force && Date.now() - readyAt.current < 20000)
      return Promise.resolve();
    if (readiness.current) return readiness.current;
    const indicator = setTimeout(() => setServerStarting(true), 1200);
    readiness.current = (async () => {
      try {
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            const response = await fetch("/api/backend/ready", {
              method: "GET",
              cache: "no-store",
              signal: AbortSignal.timeout(60000),
            });
            if (response.ok && (await response.json()).status === "ready") {
              readyAt.current = Date.now();
              setServerUnavailable(false);
              setError((current) =>
                current === serverUnavailableMessage ? "" : current,
              );
              return;
            }
          } catch {
            // Only this read-only readiness request is retried.
          }
          if (attempt < 2)
            await new Promise((resolve) => setTimeout(resolve, 1500));
        }
        setServerUnavailable(true);
        setConnection("Disconnected");
        setError(serverUnavailableMessage);
        throw new Error(serverUnavailableMessage);
      } finally {
        clearTimeout(indicator);
        setServerStarting(false);
        readiness.current = null;
      }
    })();
    return readiness.current;
  }, []);

  const api = useCallback(
    async (path: string, init: RequestInit = {}) => {
      await ensureReady();
      const session = await client.current?.auth.getSession();
      const token =
        developmentToken.current || session?.data.session?.access_token;
      if (!token)
        throw new Error("Your session has expired. Reconnect to continue.");
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${token}`);
      if (workspace.current) headers.set("X-Workspace-Id", workspace.current);
      headers.set("X-Demo-Role", currentRole.current);
      if (init.body && !(init.body instanceof FormData))
        headers.set("Content-Type", "application/json");
      const response = await fetch(`/api/backend/${path}`, {
        ...init,
        headers,
        cache: "no-store",
      });
      if (!response.ok) {
        if (response.status >= 500) readyAt.current = 0;
        const body = await response.json().catch(() => ({}));
        throw new RequestError(
          typeof body.detail === "string"
            ? body.detail
            : `The request could not be completed (${response.status}).`,
          response.status,
        );
      }
      return response;
    },
    [ensureReady],
  );
  const refresh = useCallback(async () => {
    const requestedRole = currentRole.current;
    const requestedWorkspace = workspace.current;
    const [nextSnapshot, history] = await Promise.all([
      api("snapshot").then((r) => r.json()),
      api("runs").then((r) => r.json()),
    ]);
    if (
      requestedRole !== currentRole.current ||
      requestedWorkspace !== workspace.current
    )
      return;
    setSnapshot(nextSnapshot);
    setRuns(history.runs || []);
    setConnection("Connected");
  }, [api]);
  const initialize = useCallback(async () => {
    setLoading(true);
    setError("");
    setConnection("Connecting");
    try {
      const config = await fetch("/api/config", { cache: "no-store" }).then(
        (r) => r.json(),
      );
      if (!config.backendConfigured)
        throw new Error(
          "This deployment is waiting for its assistant service configuration. No demonstration records have been loaded.",
        );
      await ensureReady();
      if (config.localAuth === true) {
        let token = sessionStorage.getItem(
          "practice-assistant-development-token",
        );
        if (!token) {
          const response = await fetch("/api/backend/dev-session", {
            method: "POST",
          });
          const result = await response.json();
          if (!response.ok || !result.access_token)
            throw new Error(
              result.detail ||
                "The local development identity could not be started.",
            );
          token = result.access_token;
          sessionStorage.setItem(
            "practice-assistant-development-token",
            token!,
          );
        }
        developmentToken.current = token!;
        setLocalIdentity(true);
      } else {
        developmentToken.current = "";
        setLocalIdentity(false);
        if (!config.supabaseUrl || !config.supabaseAnonKey)
          throw new Error(
            "This deployment is waiting for its database configuration. No demonstration records have been loaded.",
          );
        client.current ||= createClient(
          config.supabaseUrl,
          config.supabaseAnonKey,
        );
        const { data, error: sessionError } =
          await client.current.auth.getSession();
        if (sessionError) throw sessionError;
        if (!data.session) {
          const { error: signInError } =
            await client.current.auth.signInAnonymously();
          if (signInError)
            throw new Error(
              `Could not start a private demonstration session: ${signInError.message}`,
            );
        }
      }
      const storageKey =
        config.localAuth === true
          ? "practice-assistant-development-workspace"
          : "practice-assistant-workspace";
      const stored = localStorage.getItem(storageKey);
      const savedRole = localStorage.getItem("practice-assistant-role");
      const initialRole: Role = ["doctor", "coordinator", "editor"].includes(
        savedRole || "",
      )
        ? (savedRole as Role)
        : "doctor";
      currentRole.current = initialRole;
      setRole(initialRole);
      let session;
      try {
        session = await api("session", {
          method: "POST",
          body: JSON.stringify({
            workspace_id: stored || undefined,
            role: initialRole,
          }),
        }).then((r) => r.json());
      } catch (error) {
        if (
          !stored ||
          !(error instanceof RequestError) ||
          ![403, 404].includes(error.status)
        )
          throw error;
        session = await api("session", {
          method: "POST",
          body: JSON.stringify({ role: initialRole }),
        }).then((r) => r.json());
      }
      workspace.current = session.workspace_id;
      localStorage.setItem(storageKey, session.workspace_id);
      setSnapshot(session.snapshot);
      setConnection("Connected");
      const history = await api("runs").then((r) => r.json());
      setRuns(history.runs || []);
      const latest = history.runs?.[0];
      if (latest) setRun(await api(`runs/${latest.id}`).then((r) => r.json()));
    } catch (error) {
      setError(errorText(error));
      setConnection("Disconnected");
    } finally {
      setLoading(false);
    }
  }, [api, ensureReady]);

  async function retryConnection() {
    if (!snapshot) {
      void initialize();
      return;
    }
    setBusy("reconnect");
    setError("");
    try {
      await ensureReady(true);
      await refresh();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true;
      void initialize();
    }
  }, [initialize]);
  useEffect(() => {
    if (!snapshot?.workspace_id) return;
    const channel = client.current
      ?.channel(`office-${snapshot.workspace_id}`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "pa_workspaces",
          filter: `id=eq.${snapshot.workspace_id}`,
        },
        () => {
          void refresh().catch(() => setConnection("Reconnecting"));
        },
      )
      .subscribe();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible")
        void refresh().catch(() => setConnection("Reconnecting"));
    }, 15000);
    return () => {
      window.clearInterval(timer);
      if (channel) void client.current?.removeChannel(channel);
    };
  }, [snapshot?.workspace_id, refresh]);
  useEffect(() => {
    if (
      !run ||
      !["queued", "running", "awaiting_approval"].includes(run.status)
    )
      return;
    const timer = window.setTimeout(
      async () => {
        try {
          const next = await api(`runs/${run.id}`).then((r) => r.json());
          setRun(next);
          setConnection("Connected");
          if (next.status !== run.status) await refresh();
        } catch (error) {
          setError(errorText(error));
          setConnection("Reconnecting");
          setRun((current) => (current ? { ...current } : null));
        }
      },
      run.status === "awaiting_approval" ? 2500 : 1000,
    );
    return () => window.clearTimeout(timer);
  }, [run, api, refresh]);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 6500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  useEffect(() => {
    const panel = document.querySelector(".assistant-conversation");
    if (panel) panel.scrollTop = 0;
  }, [run?.id, showHistory]);
  useEffect(() => {
    setExportLink("");
  }, [run?.id]);
  useEffect(
    () => () => {
      microphone.current?.getTracks().forEach((track) => track.stop());
      if (recordingTimer.current) clearTimeout(recordingTimer.current);
      audioPlayer.current?.pause();
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
    },
    [],
  );
  useEffect(() => {
    if (!showControls && !showInspector) return;
    const previous = document.activeElement as HTMLElement | null;
    const modal = document.querySelector<HTMLElement>('[role="dialog"]');
    const focusable = () =>
      Array.from(
        modal?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input, textarea, select, summary, [tabindex="0"]',
        ) || [],
      );
    focusable()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowControls(false);
        setShowInspector(false);
      }
      if (event.key === "Tab") {
        const items = focusable();
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [showControls, showInspector]);

  async function requestWork(text: string) {
    if (!text.trim() || busy || isActive(run)) return;
    setBusy("request");
    setError("");
    setShowHistory(false);
    setMessage("");
    try {
      const created = await api("runs", {
        method: "POST",
        body: JSON.stringify({ message: text.trim() }),
      }).then((r) => r.json());
      setRun({ ...created, message: text.trim(), steps: [] });
      if (window.innerWidth <= 880)
        document
          .querySelector(".assistant-panel")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      await refresh();
    } catch (error) {
      setError(errorText(error));
      setMessage(text);
    } finally {
      setBusy("");
    }
  }
  async function approve() {
    if (!run?.plan) return;
    setBusy("approve");
    setError("");
    try {
      await api(`plans/${run.plan.id}/approve`, { method: "POST" });
      setRun(await api(`runs/${run.id}`).then((r) => r.json()));
      await refresh();
    } catch (error) {
      setError(errorText(error));
      try {
        setRun(await api(`runs/${run.id}`).then((r) => r.json()));
      } catch {
        /* The original error remains visible. */
      }
    } finally {
      setBusy("");
    }
  }
  async function cancel() {
    if (!run) return;
    setBusy("cancel");
    try {
      const result = await api(`runs/${run.id}/cancel`, {
        method: "POST",
      }).then((r) => r.json());
      setRun(result);
      await refresh();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function changeRole(nextRole: Role) {
    setBusy("role");
    setError("");
    try {
      const session = await api("session", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspace.current,
          role: nextRole,
        }),
      }).then((r) => r.json());
      currentRole.current = nextRole;
      setRole(nextRole);
      setSnapshot(session.snapshot);
      setRun(null);
      setRuns([]);
      localStorage.setItem("practice-assistant-role", nextRole);
      const history = await api("runs").then((r) => r.json());
      setRuns(history.runs || []);
      setNotice(
        `Viewing this demonstration as ${ROLE_LABELS[nextRole].toLowerCase()}.`,
      );
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function scenario(name: string) {
    setBusy(name);
    setError("");
    try {
      setSnapshot(
        await api("scenarios", {
          method: "POST",
          body: JSON.stringify({ scenario: name }),
        }).then((r) => r.json()),
      );
      if (run) setRun(await api(`runs/${run.id}`).then((r) => r.json()));
      await refresh();
      setNotice(
        `${SCENARIOS.find((item) => item.value === name)?.label || "Update"} applied to your demonstration.`,
      );
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function reset() {
    if (
      !window.confirm(
        "Reset this fictional office and clear its saved runs, approvals and preferences? Other visitors are unaffected.",
      )
    )
      return;
    setBusy("reset");
    setError("");
    try {
      setSnapshot(await api("reset", { method: "POST" }).then((r) => r.json()));
      setRun(null);
      setRuns([]);
      setMessage("");
      setNotice("Your fictional office has been reset.");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function savePreference(id: string, remove = false) {
    if (remove && !window.confirm("Remove this saved preference?")) return;
    setBusy(`memory-${id}`);
    setError("");
    try {
      setSnapshot(
        await api(`preferences/${id}`, {
          method: remove ? "DELETE" : "POST",
          body: remove ? undefined : JSON.stringify({ value: preferenceDraft }),
        }).then((r) => r.json()),
      );
      setEditingPreference(null);
      setNotice(remove ? "Preference removed." : "Preference updated.");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function selectRun(id: string) {
    setBusy("history");
    setError("");
    try {
      setRun(await api(`runs/${id}`).then((r) => r.json()));
      setShowHistory(false);
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function checkSource(id: string) {
    setBusy(`source-${id}`);
    setError("");
    try {
      const result = await api(`sources/${id}/check`, { method: "POST" }).then(
        (response) => response.json(),
      );
      await refresh();
      setNotice(
        result.status === "reachable"
          ? "The public page was reached. Its check result is saved with the source."
          : "The public page could not be reached. Its check result is saved with the source.",
      );
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function exportRun() {
    if (!run) return;
    setBusy("export");
    setError("");
    try {
      const result = await api(`runs/${run.id}/export`, {
        method: "POST",
      }).then((response) => response.json());
      const url = new URL(result.url);
      if (url.protocol !== "https:")
        throw new Error(
          "The exported report did not return a secure download link.",
        );
      setExportLink(url.toString());
      window.open(url.toString(), "_blank", "noopener,noreferrer");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  async function toggleRecording() {
    if (recording) {
      recorder.current?.stop();
      setRecording(false);
      return;
    }
    setError("");
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error(
          "Voice recording is unavailable in this browser. You can type the same request below.",
        );
      microphone.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/mp4",
        "audio/webm",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const mediaRecorder = new MediaRecorder(
        microphone.current,
        mimeType ? { mimeType } : undefined,
      );
      recorder.current = mediaRecorder;
      const chunks: BlobPart[] = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        if (recordingTimer.current) clearTimeout(recordingTimer.current);
        setRecording(false);
        microphone.current?.getTracks().forEach((track) => track.stop());
        setBusy("transcribe");
        try {
          const form = new FormData();
          form.append(
            "audio",
            await recordingToWav(
              new Blob(chunks, { type: mediaRecorder.mimeType }),
            ),
            "request.wav",
          );
          const result = await api("voice/transcribe", {
            method: "POST",
            body: form,
          }).then((r) => r.json());
          if (!result.text?.trim())
            throw new Error(
              "No speech was detected. Please try again or type your request.",
            );
          setMessage((current) =>
            [current, result.text.trim()].filter(Boolean).join(" "),
          );
          composer.current?.focus();
        } catch (error) {
          setError(errorText(error));
        } finally {
          setBusy("");
        }
      };
      mediaRecorder.start();
      setRecording(true);
      recordingTimer.current = setTimeout(() => {
        if (mediaRecorder.state === "recording") mediaRecorder.stop();
      }, 60000);
    } catch (error) {
      setError(errorText(error));
      microphone.current?.getTracks().forEach((track) => track.stop());
    }
  }
  async function speak() {
    if (speaking) {
      audioPlayer.current?.pause();
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
      setSpeaking(false);
      return;
    }
    if (!run?.answer) return;
    setBusy("speak");
    setError("");
    try {
      const response = await api("voice/speak", {
        method: "POST",
        body: JSON.stringify({ text: run.answer.slice(0, 2200) }),
      });
      const audio = await response.blob();
      if (!audio.size)
        throw new Error(
          "The speech service returned no audio. Your written response is still available; please try again.",
        );
      const url = URL.createObjectURL(audio);
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
      audioUrl.current = url;
      const player = new Audio(url);
      audioPlayer.current = player;
      player.onended = () => {
        URL.revokeObjectURL(url);
        setSpeaking(false);
      };
      player.onerror = () => {
        URL.revokeObjectURL(url);
        setSpeaking(false);
        setError(
          "Audio could not be played. The written response is available below.",
        );
      };
      await player.play();
      setSpeaking(true);
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy("");
    }
  }
  function navigate(nextView: View) {
    setView(nextView);
    setQuery("");
    setShowMobileNav(false);
  }
  function ask(text: string) {
    setMessage(text);
    composer.current?.focus();
    composer.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  const date = snapshot
    ? when(snapshot.clock, { weekday: "long", month: "long", day: "numeric" })
    : "Your personal practice assistant";
  const filtered = (records: OfficeRecord[]) =>
    records.filter((record) =>
      JSON.stringify(record).toLowerCase().includes(query.toLowerCase()),
    );
  const orderedEvents = [...(snapshot?.events || [])].sort((a, b) =>
    String(a.start).localeCompare(String(b.start)),
  );
  const openTasks =
    snapshot?.tasks.filter((item) => value(item, "status") !== "completed") ||
    [];
  const missingPaperwork =
    snapshot?.patient_admin.filter(
      (item) => value(item, "paperwork_status") !== "complete",
    ) || [];
  const activeContent =
    snapshot?.content.find((item) => item.id === selectedContent) ||
    snapshot?.content[0];
  const computedReports = (snapshot?.reports || []).map((report) => ({
    ...report,
    ...(report.computed &&
    typeof report.computed === "object" &&
    !Array.isArray(report.computed)
      ? (report.computed as Record<string, unknown>)
      : {}),
  }));

  return (
    <div className="app-shell">
      <button
        className={`nav-scrim ${showMobileNav ? "visible" : ""}`}
        aria-label="Close navigation"
        onClick={() => setShowMobileNav(false)}
      />
      <aside className={`sidebar ${showMobileNav ? "mobile-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            navigate("Today");
          }}
        >
          <span className="brand-mark">
            p<span>.</span>
          </span>
          <span>
            practice
            <span className="brand-caption">A little space to think.</span>
          </span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {NAV.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={`nav-item ${view === name ? "selected" : ""}`}
              aria-current={view === name ? "page" : undefined}
              onClick={() => navigate(name)}
            >
              <Icon size={18} strokeWidth={1.55} />
              <span>{name}</span>
              {name === "Tasks" && openTasks.length > 0 && (
                <span className="nav-count">{openTasks.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="demo-controls-link"
            onClick={() => setShowControls(true)}
          >
            <Settings2 size={16} /> Demo controls <ChevronRight size={14} />
          </button>
          <div className="profile">
            <span className="avatar">AM</span>
            <div>
              <strong>
                {snapshot?.doctor_name || "Practice demonstration"}
              </strong>
              <span>{ROLE_LABELS[role]} view</span>
            </div>
            <span
              className={`connection-dot ${connection === "Connected" ? "online" : ""}`}
              title={connection}
            />
          </div>
          <p className="built-by">Built by Gemechu · Independent demo</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setShowMobileNav(true)}
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">
              Workspace <ChevronRight size={12} /> <strong>{view}</strong>
            </span>
          </div>
          <div className="topbar-right">
            <button
              className="demo-label"
              onClick={() => setShowControls(true)}
            >
              <span /> Fictional office <ChevronDown size={12} />
            </button>
            <button
              className="icon-button refresh-button"
              title="Refresh office records"
              aria-label="Refresh office records"
              disabled={Boolean(busy) || !snapshot}
              onClick={() => {
                setBusy("refresh");
                void refresh()
                  .catch((error) => setError(errorText(error)))
                  .finally(() => setBusy(""));
              }}
            >
              <RefreshCw
                size={16}
                className={busy === "refresh" ? "spin" : ""}
              />
            </button>
          </div>
        </header>
        {serverStarting && snapshot && (
          <div className="notice-banner" role="status">
            <LoaderCircle className="spin" size={16} />
            Starting the demo server… This can take about a minute. Your request
            will continue when it is ready.
          </div>
        )}
        {error && (
          <div className="error-banner" role="alert">
            <div>
              <strong>We couldn’t finish that.</strong>
              <span>{error}</span>
            </div>
            {serverUnavailable && snapshot && (
              <button
                className="secondary-button"
                disabled={Boolean(busy) || serverStarting}
                onClick={() => void retryConnection()}
              >
                <RefreshCw size={14} /> Retry connection
              </button>
            )}
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="notice-banner" role="status">
            <CircleCheck size={16} /> {notice}
            <button
              className="icon-button"
              aria-label="Dismiss update"
              onClick={() => setNotice("")}
            >
              <X size={14} />
            </button>
          </div>
        )}
        {!snapshot ? (
          <div className="initial-state">
            <div className="initial-emblem">
              <AudioLines size={30} strokeWidth={1.3} />
            </div>
            <span className="eyebrow">PRACTICE ASSISTANT</span>
            <h1>
              {serverStarting
                ? "Starting the demo server…"
                : loading
                  ? "Making room for your day."
                  : "Let’s reconnect."}
            </h1>
            <p>
              {serverStarting
                ? "This demonstration can take about a minute to wake up. Your private workspace will open automatically."
                : loading
                  ? "Opening your private demonstration workspace. Its fictional records belong only to this browser’s session."
                  : "The application needs a working connection before it can show records or take action."}
            </p>
            {loading ? (
              <LoaderCircle className="spin" size={22} />
            ) : (
              <button
                className="primary-button"
                onClick={() => void retryConnection()}
              >
                <RefreshCw size={15} /> Retry connection
              </button>
            )}
          </div>
        ) : (
          <div className="workspace-columns">
            <main className="main-content" id="main-content">
              <div className="page-heading">
                <span className="eyebrow">
                  {view === "Today" ? date : "YOUR WORKSPACE"}
                </span>
                <h1>
                  {view === "Today"
                    ? role === "doctor"
                      ? `Good morning, ${snapshot.doctor_name.replace("Avery ", "")}.`
                      : `Your ${role === "editor" ? "content" : "coordination"} workspace.`
                    : view === "Memory"
                      ? "The details worth remembering."
                      : view === "Sources"
                        ? "A clear source for every answer."
                        : view === "Reports"
                          ? "See where the work stands."
                          : view}
                </h1>
                <p>
                  {
                    (
                      {
                        Today:
                          "A clear view of what’s next, and a little help moving it forward.",
                        Calendar:
                          "Clinic time, team conversations, and room for the work between.",
                        Tasks:
                          "The next steps, with someone responsible for each one.",
                        Messages:
                          "Communications inside this fictional office.",
                        Content: "From an idea to something ready for review.",
                        Team: "Progress, open questions, and decisions that need you.",
                        Memory:
                          "Preferences the assistant carries into your next conversation.",
                        Sources:
                          "Public information and demonstration notes, kept distinguishable.",
                        Reports:
                          "Live counts calculated from the records in this workspace.",
                      } as Record<View, string>
                    )[view]
                  }
                </p>
              </div>

              {view === "Today" && (
                <>
                  <div className="quick-starts">
                    {STARTERS.filter(
                      (_, index) => role !== "editor" || index === 2,
                    ).map(({ icon: Icon, title, text, request }, index) => (
                      <button
                        className="start-card"
                        key={title}
                        disabled={Boolean(busy) || isActive(run)}
                        onClick={() => void requestWork(request)}
                      >
                        <span className={`start-icon tone-${index}`}>
                          <Icon size={19} strokeWidth={1.5} />
                        </span>
                        <strong>{title}</strong>
                        <span className="start-description">{text}</span>
                        <ArrowUp size={15} className="start-arrow" />
                      </button>
                    ))}
                  </div>
                  <section className="card attention-card">
                    <div className="section-heading">
                      <div>
                        <span className="section-kicker">
                          THE MORNING BRIEF
                        </span>
                        <h2>A few things to keep in view</h2>
                      </div>
                      <span className="time-label">
                        <Clock3 size={12} /> {when(snapshot.clock)} PDT
                      </span>
                    </div>
                    <div className="brief-stats">
                      <button onClick={() => navigate("Tasks")}>
                        <strong>{snapshot.stats.open_tasks}</strong>
                        <span>open tasks</span>
                      </button>
                      <button
                        onClick={() =>
                          navigate(role === "editor" ? "Content" : "Calendar")
                        }
                      >
                        <strong>{snapshot.stats.needs_attention}</strong>
                        <span>need attention</span>
                      </button>
                      <button onClick={() => navigate("Content")}>
                        <strong>{snapshot.stats.content_in_review}</strong>
                        <span>in review</span>
                      </button>
                    </div>
                    {missingPaperwork.map((item) => {
                      const appointment = snapshot.events.find(
                        (event) => event.id === item.appointment_id,
                      );
                      const deadline = appointment?.start
                        ? new Date(String(appointment.start)).getTime() -
                          86400000
                        : null;
                      const minutes = deadline
                        ? Math.round(
                            (deadline - new Date(snapshot.clock).getTime()) /
                              60000,
                          )
                        : null;
                      return (
                        <div className="attention-row" key={item.id}>
                          <span className="attention-dot amber" />
                          <div>
                            <strong>Paperwork is still outstanding</strong>
                            <p>
                              {value(item, "patient_name")} ·{" "}
                              {appointment
                                ? when(appointment.start, {
                                    weekday: "short",
                                    hour: "numeric",
                                    minute: "2-digit",
                                  })
                                : "Upcoming appointment"}
                            </p>
                            {minutes !== null && (
                              <span className="deadline-text">
                                {minutes >= 0
                                  ? `${minutes} minutes until the preparation deadline`
                                  : `${Math.abs(minutes)} minutes past the preparation deadline`}
                              </span>
                            )}
                          </div>
                          <button
                            className="text-button"
                            disabled={Boolean(busy) || isActive(run)}
                            onClick={() =>
                              void requestWork(STARTERS[0].request)
                            }
                          >
                            Review <ArrowRight size={14} />
                          </button>
                        </div>
                      );
                    })}
                    {snapshot.engineering
                      .filter((item) => item.decision_needed)
                      .slice(0, 2)
                      .map((item) => (
                        <div className="attention-row" key={item.id}>
                          <span className="attention-dot teal" />
                          <div>
                            <strong>{value(item, "title")}</strong>
                            <p>
                              {typeof item.decision_needed === "string"
                                ? value(item, "decision_needed")
                                : "A team decision needs your input."}
                            </p>
                          </div>
                          <button
                            className="text-button"
                            onClick={() => navigate("Team")}
                          >
                            View <ArrowRight size={14} />
                          </button>
                        </div>
                      ))}
                    {!missingPaperwork.length &&
                      !snapshot.engineering.some(
                        (item) => item.decision_needed,
                      ) && (
                        <div className="quiet-row">
                          <CircleCheck size={18} />
                          <span>
                            No outstanding preparation or team decisions in this
                            view.
                          </span>
                        </div>
                      )}
                    <div className="card-footnote">
                      <ShieldCheck size={13} /> Changes are shown for your
                      approval before they are applied.
                    </div>
                  </section>
                  <section className="card">
                    <div className="section-heading">
                      <div>
                        <span className="section-kicker">ON THE CALENDAR</span>
                        <h2>Your next appointments</h2>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("Calendar")}
                      >
                        View calendar <ArrowRight size={14} />
                      </button>
                    </div>
                    {orderedEvents.slice(0, 4).map((event) => (
                      <div className="schedule-row" key={event.id}>
                        <div className="schedule-time">
                          <strong>{when(event.start)}</strong>
                          <span>
                            {when(event.start, {
                              month: "short",
                              day: "numeric",
                            })}
                          </span>
                        </div>
                        <span
                          className={`event-line ${value(event, "event_type")}`}
                        />
                        <div>
                          <strong>{value(event, "title")}</strong>
                          <p>
                            {value(event, "owner")} ·{" "}
                            {label(value(event, "event_type"))}
                          </p>
                        </div>
                        {value(event, "event_type") === "patient" && (
                          <span className="protected-tag">
                            <ShieldCheck size={11} /> Protected
                          </span>
                        )}
                      </div>
                    ))}
                    {!orderedEvents.length && (
                      <Empty
                        title="A clear calendar"
                        text="No events are visible for this role."
                        icon={CalendarDays}
                      />
                    )}
                  </section>
                </>
              )}

              {view === "Calendar" && (
                <>
                  <div className="view-toolbar">
                    <span className="subtle-label">
                      All times in Los Angeles · Demonstration clock
                    </span>
                    <button
                      className="secondary-button"
                      onClick={() =>
                        ask(
                          "Find a suitable time for the engineering meeting that respects my preferences and clinic appointments.",
                        )
                      }
                    >
                      <Sparkles size={14} /> Find a time
                    </button>
                  </div>
                  {[
                    ...new Set(
                      orderedEvents.map((item) =>
                        when(item.start, {
                          weekday: "long",
                          month: "long",
                          day: "numeric",
                        }),
                      ),
                    ),
                  ].map((day) => (
                    <section className="calendar-day" key={day}>
                      <h2>{day}</h2>
                      <div className="card">
                        {orderedEvents
                          .filter(
                            (item) =>
                              when(item.start, {
                                weekday: "long",
                                month: "long",
                                day: "numeric",
                              }) === day,
                          )
                          .map((item) => (
                            <div className="calendar-event" key={item.id}>
                              <div className="schedule-time">
                                <strong>{when(item.start)}</strong>
                                <span>{when(item.end)}</span>
                              </div>
                              <div
                                className={`calendar-event-body ${value(item, "event_type")}`}
                              >
                                <div>
                                  <span className="section-kicker">
                                    {label(value(item, "event_type"))}
                                  </span>
                                  <h3>{value(item, "title")}</h3>
                                  <p>{value(item, "owner")}</p>
                                </div>
                                {value(item, "event_type") === "patient" ? (
                                  <span className="protected-tag">
                                    <ShieldCheck size={12} /> Clinic time
                                    protected
                                  </span>
                                ) : (
                                  <button
                                    className="icon-button"
                                    aria-label={`Discuss ${value(item, "title")}`}
                                    onClick={() =>
                                      ask(
                                        `Review the ${value(item, "title")} meeting and suggest a time that fits the schedule.`,
                                      )
                                    }
                                  >
                                    <ArrowRight size={17} />
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                      </div>
                    </section>
                  ))}
                  {!orderedEvents.length && (
                    <Empty
                      title="No events in this view"
                      text="The content editor can see recording time, while clinic appointments remain private."
                      icon={CalendarDays}
                    />
                  )}
                </>
              )}

              {view === "Tasks" && (
                <>
                  <div className="view-toolbar">
                    <div className="segmented">
                      {["all", "open", "completed"].map((filter) => (
                        <button
                          className={taskFilter === filter ? "active" : ""}
                          key={filter}
                          onClick={() => setTaskFilter(filter)}
                        >
                          {label(filter)}
                        </button>
                      ))}
                    </div>
                    <button
                      className="secondary-button"
                      onClick={() =>
                        ask("Help me create and assign a follow-up task.")
                      }
                    >
                      <Plus size={14} /> Add with assistant
                    </button>
                  </div>
                  <div className="card records-list">
                    {filtered(snapshot.tasks)
                      .filter(
                        (item) =>
                          taskFilter === "all" || item.status === taskFilter,
                      )
                      .map((item) => (
                        <div className="task-row" key={item.id}>
                          {item.status === "completed" ? (
                            <CircleCheck
                              className="task-check complete"
                              size={20}
                            />
                          ) : (
                            <Circle className="task-check" size={20} />
                          )}
                          <div className="record-main">
                            <h3>{value(item, "title")}</h3>
                            <p>
                              {value(item, "owner") || "Unassigned"}
                              {item.due_at
                                ? ` · Due ${when(item.due_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
                                : ""}
                            </p>
                          </div>
                          <Status status={value(item, "status")} />
                        </div>
                      ))}
                    {!filtered(snapshot.tasks).filter(
                      (item) =>
                        taskFilter === "all" || item.status === taskFilter,
                    ).length && (
                      <Empty
                        title="Nothing in this list"
                        text="Try another filter, or ask the assistant to prepare your next steps."
                        icon={ListChecks}
                      />
                    )}
                  </div>
                </>
              )}

              {view === "Messages" && (
                <>
                  <div className="search-input">
                    <Search size={16} />
                    <input
                      aria-label="Search messages"
                      placeholder="Search communications"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </div>
                  <div className="card records-list">
                    {filtered(snapshot.messages).map((item) => (
                      <div className="message-record" key={item.id}>
                        <button
                          className="message-summary"
                          onClick={() =>
                            setExpandedMessage(
                              expandedMessage === item.id ? null : item.id,
                            )
                          }
                          aria-expanded={expandedMessage === item.id}
                        >
                          <span className="message-avatar">
                            {value(item, "sender").slice(0, 1).toUpperCase() ||
                              "M"}
                          </span>
                          <div className="record-main">
                            <span className="message-sender">
                              {value(item, "sender")}
                            </span>
                            <h3>{value(item, "subject")}</h3>
                            <p>{value(item, "body").slice(0, 110)}</p>
                          </div>
                          <ChevronDown
                            className={
                              expandedMessage === item.id ? "rotated" : ""
                            }
                            size={16}
                          />
                        </button>
                        {expandedMessage === item.id && (
                          <div className="message-body">
                            <div className="message-meta">
                              To {value(item, "recipient")}{" "}
                              <Status status={value(item, "status")} />
                            </div>
                            <p>{value(item, "body")}</p>
                            <button
                              className="text-button"
                              onClick={() =>
                                ask(
                                  `Review the message titled "${value(item, "subject")}" and propose an appropriate follow-up.`,
                                )
                              }
                            >
                              Prepare follow-up <ArrowRight size={13} />
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                    {!filtered(snapshot.messages).length && (
                      <Empty
                        title={
                          role === "editor"
                            ? "Office messages are private"
                            : "No messages found"
                        }
                        text={
                          role === "editor"
                            ? "This role works with content and public sources. Switch roles in Demo controls to inspect office communications."
                            : "Try a different search, or prepare a demonstration message with the assistant."
                        }
                      />
                    )}
                  </div>
                  <p className="page-note">
                    Messages stay inside this fictional office. No email or text
                    is sent to external recipients.
                  </p>
                </>
              )}

              {view === "Content" && (
                <>
                  <div className="view-toolbar">
                    <span className="subtle-label">
                      {snapshot.content.length}{" "}
                      {snapshot.content.length === 1 ? "piece" : "pieces"} in
                      the workspace
                    </span>
                    <button
                      className="secondary-button"
                      onClick={() => ask(STARTERS[2].request)}
                    >
                      <Plus size={14} /> Develop an idea
                    </button>
                  </div>
                  {snapshot.content.length > 0 ? (
                    <>
                      <div className="content-tabs">
                        {snapshot.content.map((item) => (
                          <button
                            className={
                              activeContent?.id === item.id ? "active" : ""
                            }
                            key={item.id}
                            onClick={() => setSelectedContent(item.id)}
                          >
                            <FileText size={15} />
                            <span>{value(item, "title")}</span>
                          </button>
                        ))}
                      </div>
                      {activeContent && (
                        <article className="card content-detail">
                          <div className="content-meta">
                            <Status status={value(activeContent, "status")} />
                            <span>
                              Reviewer ·{" "}
                              {value(activeContent, "reviewer") ||
                                "Not assigned"}
                            </span>
                          </div>
                          <h2>{value(activeContent, "title")}</h2>
                          <span className="section-kicker">SCRIPT</span>
                          <div className="prose">
                            <ReactMarkdown>
                              {value(activeContent, "script") ||
                                "A script has not been prepared yet."}
                            </ReactMarkdown>
                          </div>
                          <div className="caption-block">
                            <span className="section-kicker">CAPTION</span>
                            <p>
                              {value(activeContent, "caption") ||
                                "A caption has not been prepared yet."}
                            </p>
                          </div>
                          <div className="source-list">
                            {snapshot.sources
                              .filter(
                                (source) =>
                                  Array.isArray(activeContent.source_ids) &&
                                  activeContent.source_ids.includes(source.id),
                              )
                              .map((source) => (
                                <SourceLink source={source} key={source.id} />
                              ))}
                          </div>
                          <button
                            className="text-button"
                            onClick={() =>
                              ask(
                                `Review the content titled "${value(activeContent, "title")}" against its sources and suggest any improvements.`,
                              )
                            }
                          >
                            Review with assistant <ArrowRight size={14} />
                          </button>
                        </article>
                      )}
                    </>
                  ) : (
                    <Empty
                      title="Your next idea starts here"
                      text="Ask the assistant to turn a thought into a sourced script, caption, and production task."
                      icon={FileText}
                    />
                  )}
                </>
              )}

              {view === "Team" && (
                <>
                  <div className="view-toolbar">
                    <span className="subtle-label">
                      Engineering and operations
                    </span>
                    <button
                      className="secondary-button"
                      onClick={() => ask(STARTERS[1].request)}
                    >
                      <Sparkles size={14} /> Prepare my update
                    </button>
                  </div>
                  {snapshot.engineering.map((item) => (
                    <article className="card team-card" key={item.id}>
                      <div className="team-card-top">
                        <span className="team-avatar">
                          {value(item, "owner").slice(0, 1)}
                        </span>
                        <span>{value(item, "owner")}</span>
                        <Status status={value(item, "status")} />
                      </div>
                      <h2>{value(item, "title")}</h2>
                      <p>{value(item, "summary")}</p>
                      {Boolean(item.decision_needed) && (
                        <div className="decision-box">
                          <span className="section-kicker">YOUR INPUT</span>
                          <p>
                            {typeof item.decision_needed === "string"
                              ? value(item, "decision_needed")
                              : "A decision is needed to move this work forward."}
                          </p>
                          <button
                            className="text-button"
                            onClick={() =>
                              ask(
                                `Prepare a decision brief for "${value(item, "title")}" using the available engineering updates.`,
                              )
                            }
                          >
                            Prepare a decision brief <ArrowRight size={14} />
                          </button>
                        </div>
                      )}
                    </article>
                  ))}
                  {!snapshot.engineering.length && (
                    <Empty
                      title="No team records in this view"
                      text={
                        role === "editor"
                          ? "Internal engineering updates are not available to the content editor."
                          : "Team updates will appear here when they are added to the workspace."
                      }
                      icon={Users}
                    />
                  )}
                </>
              )}

              {view === "Memory" && (
                <>
                  <div className="memory-explainer">
                    <BookOpen size={22} strokeWidth={1.5} />
                    <div>
                      <strong>
                        A preference should outlast a conversation.
                      </strong>
                      <p>
                        Saved details shape future requests. You can read,
                        change, or remove them here.
                      </p>
                    </div>
                  </div>
                  <div className="view-toolbar">
                    <span className="subtle-label">
                      {snapshot.preferences.length} saved preferences
                    </span>
                    {role === "doctor" && (
                      <button
                        className="secondary-button"
                        onClick={() => ask("Remember this preference: ")}
                      >
                        <Plus size={14} /> Add a preference
                      </button>
                    )}
                  </div>
                  <div className="card records-list">
                    {snapshot.preferences.map((item) => (
                      <div className="memory-row" key={item.id}>
                        <div className="record-main">
                          <span className="section-kicker">
                            {label(value(item, "key"))}
                          </span>
                          {editingPreference === item.id ? (
                            <>
                              <textarea
                                className="memory-editor"
                                aria-label="Preference value"
                                value={preferenceDraft}
                                onChange={(event) =>
                                  setPreferenceDraft(event.target.value)
                                }
                              />
                              <div className="inline-actions">
                                <button
                                  className="primary-button small"
                                  disabled={
                                    Boolean(busy) || !preferenceDraft.trim()
                                  }
                                  onClick={() => void savePreference(item.id)}
                                >
                                  Save change
                                </button>
                                <button
                                  className="text-button"
                                  onClick={() => setEditingPreference(null)}
                                >
                                  Cancel
                                </button>
                              </div>
                            </>
                          ) : (
                            <p className="preference-value">
                              {renderValue(item.value)}
                            </p>
                          )}
                        </div>
                        {role === "doctor" && editingPreference !== item.id && (
                          <div className="inline-actions">
                            <button
                              className="text-button"
                              onClick={() => {
                                setEditingPreference(item.id);
                                setPreferenceDraft(renderValue(item.value));
                              }}
                            >
                              Edit
                            </button>
                            <button
                              className="icon-button"
                              aria-label={`Delete ${label(value(item, "key"))}`}
                              disabled={Boolean(busy)}
                              onClick={() => void savePreference(item.id, true)}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                    {!snapshot.preferences.length && (
                      <Empty
                        title="Nothing saved in this view"
                        text="Ask the assistant to remember an appropriate preference. Office preferences remain scoped to the people who can use them."
                        icon={BookOpen}
                      />
                    )}
                  </div>
                </>
              )}

              {view === "Sources" && (
                <>
                  <div className="source-explainer">
                    <ShieldCheck size={18} />
                    <p>
                      Public pages provide context for this independent
                      demonstration. Appointments, people, messages, and office
                      procedures marked “Demonstration” are fictional. This
                      application is not connected to Dr. Emer’s internal
                      systems.
                    </p>
                  </div>
                  <div className="search-input">
                    <Search size={16} />
                    <input
                      aria-label="Search sources"
                      placeholder="Find a source or topic"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </div>
                  {snapshot.sources
                    .filter((item) =>
                      `${item.title} ${item.excerpt}`
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    )
                    .map((source) => (
                      <article className="card source-card" key={source.id}>
                        <div className="source-card-top">
                          <span
                            className={`source-kind ${source.provenance === "public" ? "public" : ""}`}
                          >
                            {source.provenance === "public"
                              ? "Public source"
                              : "Demonstration"}
                          </span>
                          <span>
                            Read{" "}
                            {when(source.accessed_at, {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                            })}
                          </span>
                        </div>
                        <h2>{source.title}</h2>
                        <p>{source.excerpt}</p>
                        {source.url?.startsWith("http") && (
                          <div className="source-actions">
                            <a
                              className="text-button"
                              href={source.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open original page <ExternalLink size={13} />
                            </a>
                            <button
                              className="text-button"
                              disabled={Boolean(busy)}
                              onClick={() => void checkSource(source.id)}
                            >
                              {busy === `source-${source.id}` ? (
                                <LoaderCircle size={13} className="spin" />
                              ) : (
                                <RefreshCw size={13} />
                              )}
                              Check this source
                            </button>
                          </div>
                        )}
                        <SourceCheck source={source} />
                        <span className="source-version">
                          Source version {source.version}
                        </span>
                      </article>
                    ))}
                </>
              )}

              {view === "Reports" && (
                <>
                  <div className="report-summary">
                    <div>
                      <span className="section-kicker">OPEN TASKS</span>
                      <strong>{openTasks.length}</strong>
                      <span>of {snapshot.tasks.length} total</span>
                    </div>
                    <div>
                      <span className="section-kicker">CONTENT IN REVIEW</span>
                      <strong>
                        {
                          snapshot.content.filter(
                            (item) => item.status === "in_review",
                          ).length
                        }
                      </strong>
                      <span>of {snapshot.content.length} pieces</span>
                    </div>
                    <div>
                      <span className="section-kicker">
                        PREPARATION COMPLETE
                      </span>
                      <strong>
                        {
                          snapshot.patient_admin.filter(
                            (item) => item.paperwork_status === "complete",
                          ).length
                        }
                      </strong>
                      <span>
                        of {snapshot.patient_admin.length} visible records
                      </span>
                    </div>
                  </div>
                  <section className="card">
                    <div className="section-heading">
                      <div>
                        <span className="section-kicker">
                          WORK DISTRIBUTION
                        </span>
                        <h2>Open tasks by owner</h2>
                      </div>
                    </div>
                    <div className="owner-chart">
                      {[
                        ...new Set(
                          openTasks.map(
                            (item) => value(item, "owner") || "Unassigned",
                          ),
                        ),
                      ].map((owner) => {
                        const count = openTasks.filter(
                          (item) =>
                            (value(item, "owner") || "Unassigned") === owner,
                        ).length;
                        return (
                          <div className="owner-row" key={owner}>
                            <span>{owner}</span>
                            <div>
                              <i
                                style={{
                                  width: `${(count / Math.max(openTasks.length, 1)) * 100}%`,
                                }}
                              />
                            </div>
                            <strong>{count}</strong>
                          </div>
                        );
                      })}
                      {!openTasks.length && (
                        <p className="subtle-label">
                          No open tasks in this view.
                        </p>
                      )}
                    </div>
                    <div className="card-footnote">
                      Calculated from current records. No estimated revenue or
                      business impact.
                    </div>
                  </section>
                  <div className="view-toolbar">
                    <h2>Saved views</h2>
                    <button
                      className="secondary-button"
                      onClick={() =>
                        ask(
                          "Create and save an operational report showing open tasks by owner, preparation status, and content awaiting review.",
                        )
                      }
                    >
                      <Plus size={14} /> Save a report
                    </button>
                  </div>
                  {computedReports.map((item) => (
                    <article className="card saved-report" key={item.id}>
                      <span className="section-kicker">
                        {label(value(item, "report_type") || "Saved report")}
                      </span>
                      <h2>{value(item, "title") || "Office report"}</h2>
                      {item.total !== undefined && (
                        <p className="report-total">
                          {renderValue(item.total)} <span>records</span>
                        </p>
                      )}
                      {Array.isArray(item.by_owner) &&
                        (
                          item.by_owner as { owner: string; count: number }[]
                        ).map((entry) => (
                          <div className="report-entry" key={entry.owner}>
                            <span>{entry.owner}</span>
                            <strong>{entry.count}</strong>
                          </div>
                        ))}
                      {Array.isArray(item.rows) && (
                        <details className="report-details">
                          <summary>View {item.rows.length} report rows</summary>
                          <div className="report-records">
                            {(item.rows as OfficeRecord[]).map((row, index) => (
                              <div key={row.id || index}>
                                <strong>
                                  {value(row, "title") ||
                                    value(row, "patient_name") ||
                                    value(row, "owner") ||
                                    `Record ${index + 1}`}
                                </strong>
                                <span>
                                  {value(row, "status") ||
                                    value(row, "paperwork_status") ||
                                    value(row, "count")}
                                </span>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                    </article>
                  ))}
                  {!snapshot.reports.length && (
                    <p className="page-note">
                      Ask the assistant to save a useful view. Saved reports are
                      recalculated when you return.
                    </p>
                  )}
                </>
              )}
              <footer className="content-footer">
                <span>Independent demonstration</span>
                <span>Fictional records · Real actions · Your approval</span>
              </footer>
            </main>

            <aside className="assistant-panel" aria-label="Personal assistant">
              <div className="assistant-header">
                <div>
                  <span className="assistant-orb">
                    <Sparkles size={15} />
                  </span>
                  <strong>Your assistant</strong>
                  <span
                    className={`assistant-state ${isActive(run) ? "working" : ""}`}
                  >
                    {isActive(run) ? "Working" : "Ready"}
                  </span>
                </div>
                <div>
                  <button
                    className={`icon-button ${showHistory ? "active" : ""}`}
                    title="Previous requests"
                    aria-label="Previous requests"
                    onClick={() => setShowHistory(!showHistory)}
                  >
                    <History size={16} />
                  </button>
                  <button
                    className="icon-button"
                    title="New request"
                    aria-label="New request"
                    onClick={() => {
                      setRun(null);
                      setShowHistory(false);
                      composer.current?.focus();
                    }}
                  >
                    <Plus size={17} />
                  </button>
                </div>
              </div>
              <div className="assistant-conversation" aria-live="polite">
                {showHistory ? (
                  <div className="history-view">
                    <span className="section-kicker">PREVIOUS REQUESTS</span>
                    {runs.map((item) => (
                      <button
                        className={`history-item ${item.id === run?.id ? "active" : ""}`}
                        key={item.id}
                        disabled={Boolean(busy)}
                        onClick={() => void selectRun(item.id)}
                      >
                        <strong>{item.message}</strong>
                        <div>
                          <Status status={item.status} />
                          <span>
                            {item.created_at
                              ? when(item.created_at, {
                                  month: "short",
                                  day: "numeric",
                                })
                              : ""}
                          </span>
                        </div>
                      </button>
                    ))}
                    {!runs.length && (
                      <Empty
                        title="A fresh conversation"
                        text="Your saved requests and their outcomes will appear here."
                        icon={History}
                      />
                    )}
                  </div>
                ) : !run ? (
                  <div className="assistant-welcome">
                    <div className="welcome-orb">
                      <AudioLines size={34} strokeWidth={1.2} />
                    </div>
                    <span className="eyebrow">A LITTLE HELP, END TO END</span>
                    <h2>
                      What would you like
                      <br />
                      off your plate?
                    </h2>
                    <p>
                      I can connect the details, prepare the next steps, and
                      follow the work through.
                    </p>
                    <div className="assistant-capabilities">
                      <span>
                        <Search size={14} /> Find the right information
                      </span>
                      <span>
                        <ListChecks size={14} /> Prepare changes for your review
                      </span>
                      <span>
                        <CheckCheck size={14} /> Verify what actually changed
                      </span>
                    </div>
                    <div className="welcome-note">
                      <ShieldCheck size={14} />
                      <span>
                        You stay in control. Every proposed office change needs
                        your approval.
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="run-view">
                    <div className="user-request">
                      <span className="section-kicker">YOUR REQUEST</span>
                      <p>{run.message}</p>
                    </div>
                    <div className="run-status-line">
                      <span className="assistant-orb small-orb">
                        {isActive(run) ? (
                          <LoaderCircle size={13} className="spin" />
                        ) : (
                          <Sparkles size={13} />
                        )}
                      </span>
                      <Status status={run.status} />
                      <button
                        className="text-button inspect-link"
                        onClick={() => setShowInspector(true)}
                      >
                        <Code2 size={12} /> Inspect
                      </button>
                    </div>
                    {Boolean(run.steps?.length) && (
                      <div className="step-progress">
                        {run.steps?.slice(-5).map((step) => (
                          <div className="step-row" key={step.id}>
                            {["completed", "success", "succeeded"].includes(
                              step.status,
                            ) ? (
                              <Check size={12} />
                            ) : step.status === "running" ? (
                              <LoaderCircle size={12} className="spin" />
                            ) : (
                              <Circle size={8} />
                            )}
                            <span>{step.title || label(step.kind)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {run.answer && (
                      <div className="assistant-answer">
                        <div className="prose">
                          <ReactMarkdown
                            components={{
                              a: ({ href, children }) => (
                                <a href={href} target="_blank" rel="noreferrer">
                                  {children}
                                </a>
                              ),
                            }}
                          >
                            {run.answer}
                          </ReactMarkdown>
                        </div>
                        <button
                          className="text-button listen-button"
                          disabled={busy === "speak"}
                          onClick={() => void speak()}
                        >
                          {busy === "speak" ? (
                            <LoaderCircle size={13} className="spin" />
                          ) : speaking ? (
                            <Pause size={13} />
                          ) : (
                            <Volume2 size={13} />
                          )}
                          {speaking
                            ? "Stop reading"
                            : (run.answer?.length || 0) > 2200
                              ? "Read first part aloud"
                              : "Read aloud"}
                        </button>
                      </div>
                    )}
                    {run.plan && (
                      <div className={`approval-card ${run.plan.status}`}>
                        <div className="approval-title">
                          <ShieldCheck size={16} />
                          <strong>
                            {run.plan.status === "pending"
                              ? "Ready for your review"
                              : friendlyStatus(run.plan.status)}
                          </strong>
                        </div>
                        {run.plan.summary !== run.answer && (
                          <p>{run.plan.summary}</p>
                        )}
                        <div className="approval-actions">
                          {run.plan.actions?.map((action, index) => (
                            <details
                              className="action-detail"
                              key={action.id || index}
                              open={run.plan?.actions.length === 1}
                            >
                              <summary>
                                <span className="action-number">
                                  {[
                                    "completed",
                                    "succeeded",
                                    "success",
                                  ].includes(action.status) ? (
                                    <Check size={11} />
                                  ) : (
                                    index + 1
                                  )}
                                </span>
                                <span>
                                  {actionName(action)}
                                  <small>
                                    {String(
                                      action.payload.title ||
                                        action.payload.subject ||
                                        (action.payload.key
                                          ? label(String(action.payload.key))
                                          : "") ||
                                        "Review details",
                                    )}
                                  </small>
                                </span>
                                <ChevronDown size={13} />
                              </summary>
                              <dl>
                                {Object.entries(action.payload)
                                  .filter(
                                    ([key]) =>
                                      ![
                                        "expected_version",
                                        "expected_versions",
                                        "operation_id",
                                        "record_id",
                                      ].includes(key),
                                  )
                                  .map(([key, val]) => (
                                    <div key={key}>
                                      <dt>{actionLabel(key)}</dt>
                                      <dd>{actionValue(key, val, snapshot)}</dd>
                                    </div>
                                  ))}
                              </dl>
                              {action.status !== "proposed" && (
                                <Status status={action.status} />
                              )}
                              {action.error && (
                                <p className="inline-error">{action.error}</p>
                              )}
                            </details>
                          ))}
                        </div>
                        {run.plan.status === "pending" &&
                          run.status === "awaiting_approval" && (
                            <>
                              <button
                                className="primary-button approve-button"
                                disabled={Boolean(busy)}
                                onClick={() => void approve()}
                              >
                                {busy === "approve" ? (
                                  <LoaderCircle className="spin" size={15} />
                                ) : (
                                  <CheckCheck size={15} />
                                )}
                                Approve {run.plan.actions.length}{" "}
                                {run.plan.actions.length === 1
                                  ? "change"
                                  : "changes"}
                              </button>
                              <p className="approval-note">
                                Applies to this fictional office only.
                              </p>
                            </>
                          )}
                        {["stale", "expired"].includes(run.plan.status) && (
                          <button
                            className="secondary-button"
                            disabled={Boolean(busy) || isActive(run)}
                            onClick={() =>
                              void requestWork(
                                `Recheck the current records and prepare a fresh plan for my earlier request: ${run.message}`,
                              )
                            }
                          >
                            <RefreshCw size={14} /> Recheck and prepare a new
                            plan
                          </button>
                        )}
                      </div>
                    )}
                    {run.error && (
                      <div className="run-error">
                        <strong>This request needs attention.</strong>
                        <p>{run.error}</p>
                      </div>
                    )}
                    {isActive(run) && (
                      <button
                        className="text-button cancel-button"
                        disabled={Boolean(busy)}
                        onClick={() => void cancel()}
                      >
                        <Square size={10} /> Stop this request
                      </button>
                    )}
                    {["failed", "partial"].includes(run.status) && (
                      <button
                        className="secondary-button"
                        disabled={Boolean(busy)}
                        onClick={() => {
                          if (run.plan?.status === "partial") void approve();
                          else
                            void requestWork(
                              `Check what has already completed, avoid duplicating any saved actions, and finish the remaining work for: ${run.message}`,
                            );
                        }}
                      >
                        <RefreshCw size={14} />
                        {run.plan?.status === "partial"
                          ? "Resume remaining changes"
                          : "Review and continue"}
                      </button>
                    )}
                    {run.status === "completed" && (
                      <div className="completion-note">
                        <CheckCheck size={14} />
                        <span>Saved in your request history.</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  void requestWork(message);
                }}
              >
                <div className={`composer-box ${recording ? "recording" : ""}`}>
                  <label className="sr-only" htmlFor="request">
                    Your request
                  </label>
                  <textarea
                    ref={composer}
                    id="request"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder={
                      recording
                        ? "Listening… stop when you’re ready."
                        : "Tell me what you need…"
                    }
                    rows={3}
                    disabled={busy === "transcribe"}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        void requestWork(message);
                      }
                    }}
                  />
                  <div className="composer-tools">
                    <button
                      type="button"
                      className={`voice-button ${recording ? "listening" : ""}`}
                      aria-label={
                        recording
                          ? "Stop voice recording"
                          : "Record a voice request"
                      }
                      disabled={Boolean(busy) && busy !== "request"}
                      onClick={() => void toggleRecording()}
                    >
                      {busy === "transcribe" ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : recording ? (
                        <Square size={12} />
                      ) : (
                        <Mic size={16} />
                      )}
                      <span>
                        {busy === "transcribe"
                          ? "Transcribing"
                          : recording
                            ? "Stop recording"
                            : "Speak"}
                      </span>
                    </button>
                    <button
                      className="send-button"
                      type="submit"
                      aria-label="Send request"
                      disabled={
                        !message.trim() ||
                        Boolean(busy) ||
                        isActive(run) ||
                        recording
                      }
                    >
                      {busy === "request" ? (
                        <LoaderCircle size={17} className="spin" />
                      ) : (
                        <ArrowUp size={19} />
                      )}
                    </button>
                  </div>
                </div>
                <div className="composer-footer">
                  <span
                    className={`connection-dot ${connection === "Connected" ? "online" : ""}`}
                  />
                  {connection === "Connected"
                    ? localIdentity
                      ? "Local development identity"
                      : "Private demonstration session"
                    : connection}
                  <span>Enter to send</span>
                </div>
              </form>
            </aside>
          </div>
        )}
      </div>

      {showControls && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowControls(false);
          }}
        >
          <section
            className="modal controls-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="controls-title"
          >
            <div className="modal-heading">
              <div>
                <span className="eyebrow">EXPLORE HOW IT WORKS</span>
                <h2 id="controls-title">Demonstration controls</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close demonstration controls"
                onClick={() => setShowControls(false)}
              >
                <X size={19} />
              </button>
            </div>
            <p className="modal-intro">
              Each visitor gets an isolated fictional office. Public practice
              information supplies context; there is no connection to the
              employer’s private systems.
            </p>
            {error && (
              <div className="modal-error" role="alert">
                {error}
              </div>
            )}
            <div className="control-section">
              <h3>Choose a role</h3>
              <p>The API checks what each role can read and change.</p>
              <div className="role-choices">
                {(["doctor", "coordinator", "editor"] as Role[]).map((item) => (
                  <button
                    className={role === item ? "selected" : ""}
                    disabled={Boolean(busy) || !snapshot}
                    key={item}
                    onClick={() => void changeRole(item)}
                  >
                    <span>{ROLE_LABELS[item]}</span>
                    {role === item && <Check size={14} />}
                  </button>
                ))}
              </div>
            </div>
            <div className="control-section">
              <h3>Change the situation</h3>
              <p>
                Apply an event and observe how the assistant handles fresh
                state.
              </p>
              {SCENARIOS.map((item) => (
                <button
                  className="scenario-button"
                  key={item.value}
                  disabled={
                    Boolean(busy) ||
                    !snapshot ||
                    (role === "editor" && item.value !== "content_reviewed")
                  }
                  onClick={() => void scenario(item.value)}
                >
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.description}</small>
                  </span>
                  {busy === item.value ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Play size={14} />
                  )}
                </button>
              ))}
            </div>
            <div className="demo-clock">
              <Clock3 size={16} />
              <div>
                <strong>Fixed demonstration clock</strong>
                <p>September 8, 2026 · 8:15 AM · Los Angeles</p>
              </div>
            </div>
            <div className="reset-section">
              <div>
                <strong>Start with a clean office</strong>
                <p>Clears your workspace’s records and request history.</p>
              </div>
              <button
                className="secondary-button"
                disabled={Boolean(busy) || !snapshot}
                onClick={() => void reset()}
              >
                <RefreshCw size={14} /> Reset
              </button>
            </div>
          </section>
        </div>
      )}
      {showInspector && run && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowInspector(false);
          }}
        >
          <section
            className="modal inspector-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="inspector-title"
          >
            <div className="modal-heading">
              <div>
                <span className="eyebrow">BEHIND THIS REQUEST</span>
                <h2 id="inspector-title">Run inspector</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close run inspector"
                onClick={() => setShowInspector(false)}
              >
                <X size={19} />
              </button>
            </div>
            <div className="inspector-summary">
              <Status status={run.status} />
              <code>{run.id}</code>
              <button
                className="secondary-button export-button"
                disabled={Boolean(busy)}
                onClick={() => void exportRun()}
              >
                {busy === "export" ? (
                  <LoaderCircle size={13} className="spin" />
                ) : (
                  <Download size={13} />
                )}
                Export this run
              </button>
            </div>
            {exportLink && (
              <p className="export-result">
                <a href={exportLink} target="_blank" rel="noreferrer">
                  Open exported run report <ExternalLink size={12} />
                </a>
                <span>Private download link · Available for 10 minutes</span>
              </p>
            )}
            {error && (
              <div className="modal-error" role="alert">
                {error}
              </div>
            )}
            <div className="inspector-metrics">
              <div>
                <span>Tokens</span>
                <strong>
                  {run.usage?.tokens?.toLocaleString() ?? "Not reported"}
                </strong>
              </div>
              <div>
                <span>Model cost</span>
                <strong>{money(run.usage?.cost)}</strong>
              </div>
              <div>
                <span>Model and retrieval time</span>
                <strong>
                  {run.usage?.latency_ms == null
                    ? "Not reported"
                    : `${(run.usage.latency_ms / 1000).toFixed(1)}s`}
                </strong>
              </div>
            </div>
            <p className="inspector-caption">
              Model and retrieval time excludes queue and approval waits. Actual
              activity is reported by the service. Missing measurements are not
              counted as zero.
            </p>
            <div className="inspector-steps">
              {run.steps?.map((step, index) => (
                <details key={step.id} className="inspector-step">
                  <summary>
                    <span className="action-number">{index + 1}</span>
                    <div>
                      <strong>{step.title || label(step.kind)}</strong>
                      <small>
                        {step.model || label(step.kind)}
                        {step.duration_ms != null
                          ? ` · ${step.duration_ms} ms`
                          : ""}
                      </small>
                    </div>
                    <Status status={step.status} />
                    <ChevronDown size={14} />
                  </summary>
                  {step.detail !== undefined && (
                    <pre>{renderValue(step.detail)}</pre>
                  )}
                  <div className="step-usage">
                    <span>Tokens: {step.tokens ?? "not reported"}</span>
                    <span>Cost: {money(step.cost)}</span>
                  </div>
                </details>
              ))}
              {!run.steps?.length && (
                <p className="subtle-label">No steps have been reported yet.</p>
              )}
            </div>
            {run.plan && (
              <details className="inspector-step">
                <summary>
                  <Code2 size={16} />
                  <strong>Plan and execution receipts</strong>
                  <ChevronDown size={14} />
                </summary>
                <pre>{JSON.stringify(run.plan, null, 2)}</pre>
              </details>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
