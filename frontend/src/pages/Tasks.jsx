import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Badge, Empty, Spinner, Tabs } from "../components/ui.jsx";
import { ASSIGNMENT_LABEL, CATEGORY_LABEL, PRIORITY_LABEL, TASK_STATUS_OPTIONS, deadlineState, dueLabel } from "../format.js";

// Each view maps to a backend task category. "All" shows everything except items
// that merely mention the user without affecting them.
const VIEWS = [
  { value: "mine", label: "Mine", categories: ["direct"] },
  { value: "team", label: "My team", categories: ["team"] },
  { value: "dependencies", label: "Dependencies", categories: ["dependency"] },
  { value: "all", label: "All", categories: ["direct", "team", "dependency", "uncertain"] },
];

export default function Tasks() {
  const { notify } = useApp();
  const [params, setParams] = useSearchParams();
  const highlight = params.get("task");
  const [tasks, setTasks] = useState(null);
  const [view, setView] = useState("mine");
  const [status, setStatus] = useState("");

  const load = () => api.tasks.list().then(setTasks).catch((e) => notify(e.message, "error"));
  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (highlight) {
      const el = document.getElementById(`task-${highlight}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlight, tasks]);

  if (!tasks) return <div className="page"><Spinner /></div>;

  const current = VIEWS.find((v) => v.value === view);
  const visible = tasks.filter((t) => current.categories.includes(t.category) && (!status || t.status === status));
  const counts = Object.fromEntries(VIEWS.map((v) => [v.value, tasks.filter((t) => v.categories.includes(t.category)).length]));

  const update = async (task, next) => {
    try {
      await api.tasks.update(task.id, next);
      setTasks((list) => list.map((t) => (t.id === task.id ? { ...t, status: next } : t)));
    } catch (err) {
      notify(err.message, "error");
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <h1>My Tasks</h1>
        <p>Commitments extracted from your meetings, with the transcript each one came from.</p>
      </header>

      <div className="spread" style={{ marginBottom: 20 }}>
        <Tabs
          items={VIEWS.map((v) => ({ value: v.value, label: v.label, count: counts[v.value] }))}
          value={view}
          onChange={setView}
        />
        <select className="select" style={{ width: 180 }} aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {TASK_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {visible.length === 0 && (
        <Empty title="Nothing here">
          {view === "mine" ? "No commitments assigned to you in the meetings processed so far." : "No tasks match this view."}
        </Empty>
      )}

      <ul className="list">
        {visible.map((task) => (
          <li key={task.id} id={`task-${task.id}`} className={`task-row ${highlight === task.id ? "highlight" : ""}`} style={{ padding: 16 }}>
            <TaskRow task={task} onStatus={(next) => update(task, next)} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function TaskRow({ task, onStatus }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState(null);

  const toggle = async () => {
    setOpen((o) => !o);
    if (!history) setHistory(await api.tasks.history(task.id).catch(() => []));
  };

  return (
    <div className="task-row" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 170px", gap: 16, width: "100%" }}>
      <div style={{ minWidth: 0 }}>
        <strong>{task.description}</strong>
        <div className="meta-line">
          <span>Owner: {task.assignee || "unassigned"}</span>
          <span>Due: {dueLabel(task)}</span>
          <span>{PRIORITY_LABEL[task.priority]} priority</span>
          <span>{CATEGORY_LABEL[task.category] || "Unclear"}</span>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <Badge>{ASSIGNMENT_LABEL[task.assignment_type]}</Badge>
          {deadlineState(task) === "overdue" && <Badge tone="danger">Overdue</Badge>}
          {task.meeting_id && (
            <Link to={`/meetings/${task.meeting_id}${task.evidence_ids?.[0] ? `#${task.evidence_ids[0]}` : ""}`} className="small">
              View source meeting →
            </Link>
          )}
          <button className="btn btn-ghost btn-sm" onClick={toggle} aria-expanded={open}>
            {open ? "Hide history" : "History"}
          </button>
        </div>
        {open && (
          <ul className="small muted" style={{ marginTop: 10, paddingLeft: 18 }}>
            {(history || []).length === 0 && <li>No changes recorded.</li>}
            {(history || []).map((h) => (
              <li key={h.id}>{h.detail}</li>
            ))}
          </ul>
        )}
      </div>
      <select className="select" aria-label={`Status of ${task.description}`} value={task.status} onChange={(e) => onStatus(e.target.value)}>
        {TASK_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
