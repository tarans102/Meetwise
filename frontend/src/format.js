/* Labels and formatting shared across pages. Centralised so wording stays consistent. */

export const TASK_STATUS = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
};

export const TASK_STATUS_OPTIONS = Object.entries(TASK_STATUS).map(([value, label]) => ({ value, label }));

export const CATEGORY_LABEL = {
  direct: "Mine",
  team: "My team",
  dependency: "Dependency",
  uncertain: "Unclear owner",
  not_relevant: "Other",
};

export const ASSIGNMENT_LABEL = { explicit: "Explicitly assigned", inferred: "Inferred", unassigned: "Unassigned" };

export const VERDICT_LABEL = { confirmed: "Confirmed", inferred: "Inferred", unsupported: "Needs review" };

export const PRIORITY_LABEL = { high: "High", medium: "Medium", low: "Low" };

export const EVENT_TYPE_LABEL = { meeting: "Meeting", deadline: "Deadline", general: "Event" };

export const STAGE_LABEL = {
  queued: "Queued",
  preprocess: "Reading transcript",
  metadata: "Generating title",
  summarize: "Summarising",
  segment: "Finding topics",
  extract_decisions: "Extracting decisions",
  extract_events: "Finding events",
  extract_actions: "Extracting action items",
  attribute: "Assigning ownership",
  verify: "Verifying",
  persist: "Indexing",
  completed: "Ready",
  error: "Failed",
};

export function formatDate(value) {
  if (!value) return "No date";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function dayKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function initials(name = "") {
  const letters = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  return letters || "?";
}

export function greeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

// Prefers the normalised date; falls back to the words the transcript used.
export function dueLabel(task) {
  if (task.due_on) return formatDate(task.due_on);
  return task.due_date || "not stated";
}

// null when there is no deadline or the task is done.
export function deadlineState(task, now = new Date()) {
  if (!task.due_on || task.status === "completed") return null;
  const today = dayKey(now);
  if (task.due_on < today) return "overdue";
  if (task.due_on === today) return "today";
  return "upcoming";
}

export function truncate(text = "", length = 160) {
  return text.length > length ? `${text.slice(0, length).trim()}…` : text;
}
