import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Upload } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Badge, Button, Empty, Field, Modal, Spinner } from "../components/ui.jsx";
import { formatDate, truncate } from "../format.js";
import { StatusTag } from "./Dashboard.jsx";

export default function Meetings() {
  const { notify } = useApp();
  const [meetings, setMeetings] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(() => api.meetings.list().then(setMeetings).catch((e) => notify(e.message, "error")), [notify]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is still being processed, so status updates appear without a refresh.
  useEffect(() => {
    if (!meetings?.some((m) => m.status === "queued" || m.status === "processing")) return undefined;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [meetings, load]);

  if (!meetings) return <div className="page"><Spinner /></div>;
  const filtered = meetings.filter((m) => (m.title || "").toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="page">
      <div className="spread page-head">
        <div>
          <h1>Meetings</h1>
          <p>Upload transcripts (TXT, PDF or DOCX). MeetWise reads them and keeps the results searchable.</p>
        </div>
        <Button variant="primary" onClick={() => setShowUpload(true)}><Plus size={16} /> Add transcript</Button>
      </div>

      <input
        className="input"
        style={{ maxWidth: 360, marginBottom: 20 }}
        placeholder="Filter by title"
        aria-label="Filter meetings"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {meetings.length === 0 && (
        <Empty title="No meetings yet">Add a transcript and its decisions, commitments and events will appear here.</Empty>
      )}

      <div className="stack" style={{ gap: 14 }}>
        {filtered.map((m) => (
          <Link key={m.id} to={`/meetings/${m.id}`} className="card meeting-card" style={{ color: "inherit" }}>
            <div className="spread">
              <h3>{m.title || "Untitled meeting"}</h3>
              <StatusTag meeting={m} />
            </div>
            <div className="meta-line">
              <span>{formatDate(m.meeting_date || m.created_at)}</span>
              <span>{(m.participants || []).join(", ") || "No participants listed"}</span>
              {m.status === "completed" && <Badge>{m.action_count} action {m.action_count === 1 ? "item" : "items"}</Badge>}
            </div>
            {m.executive_summary && (
              <p className="muted small" style={{ marginTop: 8 }}>{truncate(m.executive_summary, 220)}</p>
            )}
            {m.status === "error" && <p className="error-text small" style={{ marginTop: 8 }}>{m.error}</p>}
          </Link>
        ))}
      </div>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={() => {
            setShowUpload(false);
            notify("Transcript received. Processing has started.");
            load();
          }}
        />
      )}
    </div>
  );
}

function UploadModal({ onClose, onUploaded }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [participants, setParticipants] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("user_title", title.trim());
    if (date) form.append("user_date", date);
    if (participants.trim()) form.append("user_participants", participants.trim());
    try {
      await api.meetings.upload(form);
      onUploaded();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Add a transcript"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={!file || busy}>
            <Upload size={15} /> {busy ? "Uploading…" : "Process transcript"}
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 16 }}>
        <Field label="Transcript file">
          <input
            type="file"
            accept=".txt,.pdf,.docx"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </Field>
        <Field label="Title (optional — generated if left empty)">
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="grid-form">
          <Field label="Meeting date">
            <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label="Participants (comma separated)">
            <input className="input" value={participants} onChange={(e) => setParticipants(e.target.value)} />
          </Field>
        </div>
        {error && <p className="error-text small">{error}</p>}
      </div>
    </Modal>
  );
}
