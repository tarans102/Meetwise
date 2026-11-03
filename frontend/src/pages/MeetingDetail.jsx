import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Check, MessageCircle, Pencil, Trash2, X } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Badge, Button, Empty, Spinner, Tabs } from "../components/ui.jsx";
import {
  ASSIGNMENT_LABEL, EVENT_TYPE_LABEL, PRIORITY_LABEL, TASK_STATUS_OPTIONS, dueLabel,
  VERDICT_LABEL, formatDate,
} from "../format.js";
import { StatusTag } from "./Dashboard.jsx";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "transcript", label: "Transcript" },
  { value: "actions", label: "Action items" },
  { value: "decisions", label: "Decisions" },
  { value: "events", label: "Events" },
];

export default function MeetingDetail() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { openAssistant, notify } = useApp();
  const [meeting, setMeeting] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(location.hash.startsWith("#U") ? "transcript" : "overview");

  const load = async () => {
    try {
      const [m, t, p] = await Promise.all([
        api.meetings.get(id),
        api.tasks.list(),
        api.events.pending(),
      ]);
      setMeeting(m);
      setTasks(t.filter((task) => task.meeting_id === id));
      setEvents(p.filter((e) => e.source_meeting_id === id));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  // Citations link to /meetings/:id#U012. Open the transcript and scroll to that line.
  useEffect(() => {
    if (!location.hash) return;
    setTab("transcript");
    const timer = setTimeout(() => {
      const el = document.getElementById(location.hash.slice(1));
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("flash");
        setTimeout(() => el.classList.remove("flash"), 2400);
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [location.hash]);

  if (error) return <div className="page"><p className="error-text">{error}</p></div>;
  if (!meeting) return <div className="page"><Spinner /></div>;

  const result = meeting.result || {};
  const processing = meeting.status === "queued" || meeting.status === "processing";

  return (
    <div className="page">
      <Link to="/meetings" className="small muted">← Meetings</Link>
      <header className="page-head" style={{ marginTop: 12 }}>
        <div className="spread">
          <div style={{ minWidth: 0 }}>
            <TitleEditor meeting={meeting} onSaved={load} />
            <div className="meta-line">
              <span>{formatDate(meeting.meeting_date || meeting.created_at)}</span>
              <span>{(meeting.participants || []).join(", ") || "No participants listed"}</span>
              <StatusTag meeting={meeting} />
            </div>
          </div>
          <Button onClick={() => openAssistant({ type: "meeting", meetingId: id, meetingTitle: meeting.title })}>
            <MessageCircle size={15} /> Ask about this meeting
          </Button>
        </div>
      </header>

      {processing && (
        <p className="notice" role="status">Processing: {STAGE_LABEL_SAFE(meeting.stage)}. This page updates when it finishes.</p>
      )}
      {meeting.status === "error" && (
        <p className="notice error-text" role="alert">Processing failed: {meeting.error}</p>
      )}

      {meeting.status === "completed" && (
        <>
          <Tabs items={TABS} value={tab} onChange={setTab} />
          <div style={{ marginTop: 24 }}>
            {tab === "overview" && <Overview meeting={meeting} result={result} tasks={tasks} onTab={setTab} />}
            {tab === "transcript" && <Transcript meetingId={id} result={result} />}
            {tab === "actions" && <ActionItems tasks={tasks} onChanged={load} notify={notify} />}
            {tab === "decisions" && <Decisions result={result} onTab={setTab} />}
            {tab === "events" && <EventsReview events={events} onChanged={load} notify={notify} />}
          </div>
        </>
      )}
    </div>
  );
}

const STAGE_LABEL_SAFE = (stage) => ({
  queued: "queued", preprocess: "reading the transcript", metadata: "generating a title",
  summarize: "summarising", segment: "finding topics", extract_decisions: "extracting decisions",
  extract_events: "finding events", extract_actions: "extracting action items",
  attribute: "assigning ownership", verify: "verifying", persist: "indexing",
})[stage] || "working";

function TitleEditor({ meeting, onSaved }) {
  const { notify } = useApp();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(meeting.title || "");

  const save = async () => {
    try {
      await api.meetings.update(meeting.id, { title: value.trim() });
      setEditing(false);
      notify("Title saved");
      onSaved();
    } catch (err) {
      notify(err.message, "error");
    }
  };

  if (!editing) {
    return (
      <div className="row" style={{ gap: 10 }}>
        <h1>{meeting.title || "Untitled meeting"}</h1>
        <button className="icon-btn" aria-label="Edit title" onClick={() => setEditing(true)}><Pencil size={15} /></button>
        {meeting.title_generated && <Badge>Generated title</Badge>}
      </div>
    );
  }
  return (
    <div className="row">
      <input className="input" style={{ maxWidth: 420, fontFamily: "var(--font-display)", fontSize: 22 }} value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
      <button className="icon-btn" aria-label="Save title" onClick={save}><Check size={16} /></button>
      <button className="icon-btn" aria-label="Cancel" onClick={() => setEditing(false)}><X size={16} /></button>
    </div>
  );
}

function Overview({ meeting, result, tasks, onTab }) {
  const summary = result.summary || {};
  const issues = result.unresolved_issues || [];
  const decisions = result.decisions || [];
  const counts = result.verification?.counts || {};
  return (
    <div className="stack" style={{ gap: 28 }}>
      <section>
        <h2 className="section-title">Summary</h2>
        <p style={{ fontSize: 17, maxWidth: 720 }}>{summary.executive_summary || "No summary was produced."}</p>
      </section>
      <div className="grid-form" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Panel title="Key topics">
          {(result.topics || []).map((t) => <Badge key={t.name}>{t.name}</Badge>)}
          {!(result.topics || []).length && <p className="muted small">None identified.</p>}
        </Panel>
        <Panel title="Important outcomes">
          <ul className="list small">
            {(summary.outcomes || []).map((o, i) => <li key={i} style={{ padding: "6px 0" }}>{o}</li>)}
            {!(summary.outcomes || []).length && <li className="muted">No outcomes recorded.</li>}
          </ul>
        </Panel>
      </div>
      <div className="row" style={{ gap: 12 }}>
        <button className="btn btn-ghost" onClick={() => onTab("actions")}>{tasks.length} action items</button>
        <button className="btn btn-ghost" onClick={() => onTab("decisions")}>{decisions.length} decisions</button>
        <span className="btn btn-ghost" style={{ cursor: "default" }}>{issues.length} unresolved</span>
      </div>
      {issues.length > 0 && (
        <section>
          <h2 className="section-title">Unresolved issues</h2>
          <ul className="list">
            {issues.map((issue, i) => (
              <li key={i}>
                <strong>{issue.description}</strong>
                <div className="meta-line">
                  <span>{issue.responsible ? `Owner: ${issue.responsible}` : "No owner identified"}</span>
                  <span>{issue.explicitly_unresolved ? "Left open in discussion" : "Possibly unresolved"}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {(counts.unsupported || 0) > 0 && (
        <p className="notice">{counts.unsupported} extracted item{counts.unsupported > 1 ? "s" : ""} could not be verified against the transcript and are marked "Needs review".</p>
      )}
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 12 }}>{title}</h3>
      <div className="row" style={{ gap: 8 }}>{children}</div>
    </div>
  );
}

function Transcript({ meetingId, result }) {
  const [lines, setLines] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.meetings.transcript(meetingId).then(setLines).catch((err) => setError(err.message));
  }, [meetingId]);

  // Group utterances by the topic segmentation the pipeline produced.
  const groups = useMemo(() => {
    if (!lines) return [];
    const byId = new Map(lines.map((l) => [l.id, l]));
    return (result.topics || []).map((topic) => ({
      name: topic.name,
      items: topic.utterance_ids.map((uid) => byId.get(uid)).filter(Boolean),
    }));
  }, [lines, result]);

  if (error) {
    return (
      <Empty title="Transcript unavailable">{error}</Empty>
    );
  }
  if (!lines) return <Spinner />;

  const needle = query.trim().toLowerCase();
  const matches = (line) => !needle || line.text.toLowerCase().includes(needle);

  return (
    <div>
      <input className="input" style={{ maxWidth: 360, marginBottom: 20 }} placeholder="Search this transcript" aria-label="Search transcript" value={query} onChange={(e) => setQuery(e.target.value)} />
      {(groups.length ? groups : [{ name: "Transcript", items: lines }]).map((group) => (
        <section key={group.name} style={{ marginBottom: 28 }}>
          <h3 className="mono" style={{ marginBottom: 6, textTransform: "uppercase" }}>{group.name}</h3>
          {group.items.filter(matches).map((line) => (
            <div key={line.id} id={line.id} className="utterance">
              <div>
                <div className="who">{line.speaker || "Speaker"}</div>
                <div className="mono">{line.id}{line.timestamp ? ` · ${line.timestamp}` : ""}</div>
              </div>
              <div className="text">{line.text}</div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

function ActionItems({ tasks, onChanged, notify }) {
  const setStatus = async (task, status) => {
    try {
      await api.tasks.update(task.id, status);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  if (tasks.length === 0) return <Empty title="No action items">Nothing in this meeting was assigned as a task.</Empty>;

  return (
    <ul className="list">
      {tasks.map((task) => (
        <li key={task.id}>
          <div className="spread" style={{ alignItems: "flex-start" }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <strong>{task.description}</strong>
              <div className="meta-line">
                <span>Owner: {task.assignee || "unassigned"}</span>
                <span>Due: {dueLabel(task)}</span>
                <span>Priority: {PRIORITY_LABEL[task.priority]}</span>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <Badge>{ASSIGNMENT_LABEL[task.assignment_type]}</Badge>
                {task.verdict && <Badge tone={task.verdict === "unsupported" ? "danger" : task.verdict === "confirmed" ? "completed" : "amber"}>{VERDICT_LABEL[task.verdict]}</Badge>}
              </div>
              {task.verification_notes?.length > 0 && (
                <p className="muted small" style={{ marginTop: 6 }}>{task.verification_notes.join(" ")}</p>
              )}
              {task.evidence_ids?.length > 0 && (
                <p className="small" style={{ marginTop: 6 }}>
                  Evidence:{" "}
                  {task.evidence_ids.map((eid) => (
                    <Link key={eid} to={`#${eid}`} className="mono" style={{ marginRight: 8 }}>{eid}</Link>
                  ))}
                </p>
              )}
            </div>
            <select
              className="select"
              style={{ width: 160 }}
              aria-label={`Status of ${task.description}`}
              value={task.status}
              onChange={(e) => setStatus(task, e.target.value)}
            >
              {TASK_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Decisions({ result, onTab }) {
  const decisions = result.decisions || [];
  const finalized = decisions.filter((d) => d.status === "finalized");
  const pending = decisions.filter((d) => d.status !== "finalized");
  if (decisions.length === 0) return <Empty title="No decisions recorded">The meeting didn't reach or record any decisions.</Empty>;
  return (
    <div className="stack" style={{ gap: 28 }}>
      <DecisionList title="Finalised" items={finalized} />
      <DecisionList title="Pending" items={pending} />
    </div>
  );
}

function DecisionList({ title, items }) {
  if (!items.length) return null;
  return (
    <section>
      <h2 className="section-title">{title}</h2>
      <ul className="list">
        {items.map((d, i) => (
          <li key={i}>
            <strong>{d.statement}</strong>
            {d.alternatives?.length > 0 && <p className="small muted" style={{ marginTop: 4 }}>Alternatives considered: {d.alternatives.join("; ")}</p>}
            {d.rationale && <p className="small muted">Reason: {d.rationale}</p>}
            {d.evidence_ids?.length > 0 && (
              <p className="small" style={{ marginTop: 4 }}>
                {d.evidence_ids.map((eid) => <a key={eid} href={`#${eid}`} className="mono" style={{ marginRight: 8 }}>{eid}</a>)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EventsReview({ events, onChanged, notify }) {
  const [busyId, setBusyId] = useState(null);
  const confirm = async (event) => {
    setBusyId(event.id);
    try {
      await api.events.confirm(event.id);
      notify(`Added "${event.title}" to your calendar`);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusyId(null);
    }
  };
  const dismiss = async (event) => {
    setBusyId(event.id);
    try {
      await api.events.remove(event.id);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusyId(null);
    }
  };

  if (events.length === 0) {
    return <Empty title="No events to review">Events mentioned in this meeting appear here before they reach your calendar.</Empty>;
  }
  return (
    <div>
      <p className="muted small" style={{ marginBottom: 16 }}>
        These were found in the transcript. Nothing is added to your calendar until you confirm it.
      </p>
      <ul className="list">
        {events.map((e) => (
          <li key={e.id} className="spread">
            <div>
              <strong>{e.title}</strong>
              <div className="meta-line">
                <span>{EVENT_TYPE_LABEL[e.event_type]}</span>
                <span>{e.starts_at ? formatDate(e.starts_at) : `Date unclear${e.date_text ? `: "${e.date_text}"` : ""}`}</span>
                <span>Suggested as {e.extracted_confidence}</span>
              </div>
            </div>
            <div className="row">
              <Button
                variant="primary"
                size="sm"
                disabled={busyId === e.id || !e.starts_at}
                title={e.starts_at ? undefined : "Set a date on the Calendar page first"}
                onClick={() => confirm(e)}
              >
                Add to calendar
              </Button>
              <Button variant="danger" size="sm" disabled={busyId === e.id} onClick={() => dismiss(e)}><Trash2 size={13} /> Dismiss</Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
