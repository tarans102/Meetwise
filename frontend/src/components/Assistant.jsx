import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Send, X } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { formatDate, truncate } from "../format.js";
import { Badge, Button } from "./ui.jsx";

/*
 * The assistant. In "panel" mode it is a right-side overlay available from any page;
 * in "page" mode (the AI Chat page) it fills the page and shows session history.
 * Scope is shown explicitly so users always know what is being searched.
 */
export default function Assistant({ mode = "panel" }) {
  const { assistantOpen, setAssistantOpen, assistantScope, notify } = useApp();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [scopeType, setScopeType] = useState("all");
  const [busy, setBusy] = useState(false);
  const threadRef = useRef(null);
  const isPage = mode === "page";
  const visible = isPage || assistantOpen;

  useEffect(() => {
    setScopeType(assistantScope.type === "meeting" && assistantScope.meetingId ? "meeting" : "all");
  }, [assistantScope]);

  useEffect(() => {
    if (!visible) return;
    api.chat.sessions().then(setSessions).catch(() => setSessions([]));
  }, [visible]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  if (!visible) return null;

  const hasMeetingContext = Boolean(assistantScope.meetingId);

  const openSession = async (id) => {
    try {
      const session = await api.chat.session(id);
      setSessionId(id);
      setMessages(session.messages);
    } catch (err) {
      notify(err.message, "error");
    }
  };

  const newChat = () => {
    setSessionId(null);
    setMessages([]);
  };

  const send = async () => {
    const text = question.trim();
    if (!text || busy) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const response = await api.chat.ask({
        question: text,
        scope: scopeType,
        meeting_id: scopeType === "meeting" ? assistantScope.meetingId : undefined,
        session_id: sessionId || undefined,
      });
      setSessionId(response.session_id);
      setMessages((m) => [...m, response.message]);
      api.chat.sessions().then(setSessions).catch(() => {});
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: err.message, status: "error", citations: [] }]);
    } finally {
      setBusy(false);
    }
  };

  const followCitation = (link) => {
    if (!link) return;
    navigate(link);
    if (!isPage) setAssistantOpen(false);
  };

  const scopeLabel =
    scopeType === "meeting" && assistantScope.meetingTitle
      ? `This meeting: ${assistantScope.meetingTitle}`
      : "All processed meetings";

  const conversation = (
    <>
      <div className="spread">
        <div className="row" style={{ gap: 8 }}>
          <div className="segmented" role="group" aria-label="Search scope">
            <button aria-pressed={scopeType === "meeting"} disabled={!hasMeetingContext} onClick={() => setScopeType("meeting")}>
              This meeting
            </button>
            <button aria-pressed={scopeType === "all"} onClick={() => setScopeType("all")}>
              All meetings
            </button>
          </div>
        </div>
        <div className="row" style={{ gap: 6 }}>
          {isPage && (
            <Button size="sm" onClick={newChat}><Plus size={14} /> New chat</Button>
          )}
          {!isPage && (
            <button className="icon-btn" aria-label="Close assistant" onClick={() => setAssistantOpen(false)}>
              <X size={18} />
            </button>
          )}
        </div>
      </div>
      <p className="mono" style={{ marginTop: 6 }}>Searching: {scopeLabel}</p>
    </>
  );

  const thread = (
    <div className="chat-thread" ref={threadRef} aria-live="polite">
      {messages.length === 0 && !busy && (
        <div className="empty">
          <h3>Ask about your meetings</h3>
          <p>Answers cite the meeting they came from. If the transcripts don't say, you'll be told.</p>
        </div>
      )}
      {messages.map((message, index) => (
        <MessageView key={message.id || index} message={message} onFollow={followCitation} />
      ))}
      {busy && <p className="muted small">Searching your meetings…</p>}
    </div>
  );

  const composer = (
    <div className="composer">
      <textarea
        className="textarea"
        style={{ minHeight: 44, maxHeight: 140 }}
        rows={1}
        placeholder="Ask a question…"
        aria-label="Question"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
      />
      <Button variant="primary" onClick={send} disabled={busy || !question.trim()} aria-label="Send question">
        <Send size={16} />
      </Button>
    </div>
  );

  if (!isPage) {
    return (
      <aside className="assistant-panel" aria-label="MeetWise assistant">
        <div style={{ padding: "16px 16px 0" }}>
          <h2 style={{ fontSize: 22 }}>Assistant</h2>
          {conversation}
        </div>
        <div className="thread" style={{ marginTop: 12 }}>{thread}</div>
        <div className="composer-wrap">{composer}</div>
      </aside>
    );
  }

  return (
    <div className="page" style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 24, alignItems: "start" }}>
      <div className="stack" style={{ position: "sticky", top: 84 }}>
        <h3>Conversations</h3>
        {sessions.length === 0 && <p className="muted small">No conversations yet.</p>}
        {sessions.map((s) => (
          <button
            key={s.id}
            className="popover-item"
            style={{ position: "relative", background: s.id === sessionId ? "var(--color-surface)" : "none", borderRadius: 12 }}
            onClick={() => openSession(s.id)}
          >
            <span className="small">{truncate(s.title, 60)}</span>
            <span className="mono" style={{ display: "block" }}>{formatDate(s.updated_at)}</span>
          </button>
        ))}
      </div>
      <section className="card" style={{ display: "flex", flexDirection: "column", gap: 16, minHeight: "70vh" }}>
        {conversation}
        {thread}
        {composer}
      </section>
    </div>
  );
}

function MessageView({ message, onFollow }) {
  if (message.role === "user") {
    return <div className="bubble-user">{message.content}</div>;
  }
  const insufficient = message.status === "insufficient_evidence";
  const failed = message.status === "error";
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="bubble-assistant">{message.content}</div>
      {insufficient && <Badge tone="amber">Not found in your meetings</Badge>}
      {failed && <Badge tone="danger">Couldn't answer</Badge>}
      {message.citations?.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <span className="mono">Sources</span>
          {message.citations.map((c) => (
            <button key={c.source_id} className="citation" onClick={() => onFollow(c.link)} disabled={!c.link}>
              <span className="small" style={{ fontWeight: 700 }}>
                [{c.source_id}] {c.meeting_title || "Untitled meeting"}
                {c.meeting_date ? ` · ${formatDate(c.meeting_date)}` : ""}
              </span>
              <span className="small muted" style={{ display: "block", marginTop: 2 }}>
                {c.kind === "task" ? "Task record" : c.kind.replace("_", " ")}
                {c.speaker ? ` · ${c.speaker}` : ""}
                {c.timestamp ? ` · ${c.timestamp}` : ""}
              </span>
              <span className="small" style={{ display: "block", marginTop: 4 }}>{truncate(c.excerpt, 180)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
