import { useEffect, useMemo, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Badge, Button, ConfirmDialog, Empty, Field, Modal, Spinner } from "../components/ui.jsx";
import { initials } from "../format.js";

const blankPerson = () => ({
  id: crypto.randomUUID(),
  name: "",
  designation: "",
  responsibilities: [],
  ownership: [],
  aliases: [],
  manager_id: null,
  is_user: false,
});

export default function Team() {
  const { people, loadPeople, notify } = useApp();
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  const me = people.find((p) => p.is_user);
  const team = people.filter((p) => !p.is_user);
  const byManager = useMemo(() => {
    const map = {};
    people.forEach((p) => {
      const key = p.manager_id || "root";
      (map[key] ||= []).push(p);
    });
    return map;
  }, [people]);

  const remove = async () => {
    setBusy(true);
    try {
      await api.people.remove(deleting.id);
      notify(`Removed ${deleting.name}`);
      setDeleting(null);
      loadPeople();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (!people) return <div className="page"><Spinner /></div>;

  return (
    <div className="page">
      <header className="spread page-head">
        <div>
          <h1>Profile & team</h1>
          <p>MeetWise uses your responsibilities and team to decide which tasks are yours, which belong to your reports, and which depend on you.</p>
        </div>
      </header>

      <section className="card" style={{ marginBottom: 28 }}>
        <div className="spread" style={{ marginBottom: 12 }}>
          <div className="row">
            <span className="avatar" style={{ width: 48, height: 48 }}>{initials(me?.name)}</span>
            <div>
              <h3>{me?.name || "Your profile"}</h3>
              <span className="muted small">{me?.designation || "Add your role to get started"}</span>
            </div>
          </div>
          <Button onClick={() => setEditing(me ? { ...me } : { ...blankPerson(), is_user: true })}>
            <Pencil size={14} /> {me ? "Edit profile" : "Set up profile"}
          </Button>
        </div>
        {me && <PersonDetails person={me} />}
      </section>

      <section>
        <div className="spread" style={{ marginBottom: 12 }}>
          <h2 className="section-title" style={{ margin: 0 }}>Team</h2>
          <Button size="sm" onClick={() => setEditing(blankPerson())}><Plus size={14} /> Add person</Button>
        </div>
        {team.length === 0 && (
          <Empty title="No team members yet">Add the people who report to you, and anyone whose work you depend on.</Empty>
        )}
        <div className="stack" style={{ gap: 12 }}>
          {renderTree(byManager, "root", 0, (p) => (
            <PersonCard key={p.id} person={p} onEdit={() => setEditing({ ...p })} onDelete={() => setDeleting(p)} />
          ))}
        </div>
      </section>

      {editing && (
        <PersonForm
          person={editing}
          people={people}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); loadPeople(); notify("Saved"); }}
          notify={notify}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={`Remove ${deleting.name}?`}
          message="They will be removed from the team. Past meetings and tasks keep their names."
          confirmLabel="Remove"
          busy={busy}
          onCancel={() => setDeleting(null)}
          onConfirm={remove}
        />
      )}
    </div>
  );
}

// Walks the reporting tree from the top. The current user is not rendered as a row,
// but their direct reports are rendered at the top level.
function renderTree(byManager, parentKey, depth, render) {
  const children = byManager[parentKey] || [];
  return children.flatMap((p) => {
    if (p.is_user) return renderTree(byManager, p.id, depth, render);
    return [
      <div key={p.id} style={{ marginLeft: depth * 28 }}>{render(p)}</div>,
      ...renderTree(byManager, p.id, depth + 1, render),
    ];
  });
}

function PersonCard({ person, onEdit, onDelete }) {
  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="spread">
        <div className="row">
          <span className="avatar">{initials(person.name)}</span>
          <div>
            <strong>{person.name}</strong>
            <div className="muted small">{person.designation || "No role set"}</div>
          </div>
        </div>
        <div className="row">
          <button className="icon-btn" aria-label={`Edit ${person.name}`} onClick={onEdit}><Pencil size={14} /></button>
          <button className="icon-btn" aria-label={`Remove ${person.name}`} onClick={onDelete}><Trash2 size={14} /></button>
        </div>
      </div>
      <PersonDetails person={person} />
    </div>
  );
}

function PersonDetails({ person }) {
  return (
    <div className="stack" style={{ gap: 8, marginTop: 8 }}>
      {person.responsibilities?.length > 0 && (
        <div className="row"><span className="mono">Responsibilities</span>{person.responsibilities.map((r) => <Badge key={r}>{r}</Badge>)}</div>
      )}
      {person.ownership?.length > 0 && (
        <div className="row"><span className="mono">Ownership</span>{person.ownership.map((r) => <Badge key={r}>{r}</Badge>)}</div>
      )}
      {person.aliases?.length > 0 && (
        <div className="row"><span className="mono">Also appears as</span><span className="small">{person.aliases.join(", ")}</span></div>
      )}
    </div>
  );
}

const toList = (text) => text.split(",").map((s) => s.trim()).filter(Boolean);

function PersonForm({ person, people, onClose, onSaved, notify }) {
  const [form, setForm] = useState({
    ...person,
    responsibilitiesText: person.responsibilities.join(", "),
    ownershipText: person.ownership.join(", "),
    aliasesText: person.aliases.join(", "),
  });
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const save = async () => {
    setBusy(true);
    try {
      await api.people.save({
        id: form.id,
        name: form.name.trim(),
        designation: form.designation.trim(),
        responsibilities: toList(form.responsibilitiesText),
        ownership: toList(form.ownershipText),
        aliases: toList(form.aliasesText),
        manager_id: form.manager_id || null,
        is_user: Boolean(form.is_user),
      });
      onSaved();
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  };

  const managerOptions = people.filter((p) => p.id !== form.id);

  return (
    <Modal
      title={form.is_user ? "Your profile" : person.name ? `Edit ${person.name}` : "Add a team member"}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save} disabled={busy || !form.name.trim()}>Save</Button>
        </>
      }
    >
      <div className="grid-form">
        <Field label="Name"><input className="input" value={form.name} onChange={set("name")} autoFocus /></Field>
        <Field label="Designation"><input className="input" value={form.designation} onChange={set("designation")} /></Field>
        <Field label="Responsibilities (comma separated)" className="span-2">
          <input className="input" value={form.responsibilitiesText} onChange={set("responsibilitiesText")} />
        </Field>
        <Field label="Areas of ownership (comma separated)" className="span-2">
          <input className="input" value={form.ownershipText} onChange={set("ownershipText")} />
        </Field>
        <Field label="Other names used in transcripts (aliases)" className="span-2">
          <input className="input" value={form.aliasesText} onChange={set("aliasesText")} placeholder="e.g. Ravi, R. Kumar" />
        </Field>
        {!form.is_user && (
          <Field label="Reports to" className="span-2">
            <select className="select" value={form.manager_id || ""} onChange={set("manager_id")}>
              <option value="">No manager</option>
              {managerOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
        )}

      </div>
    </Modal>
  );
}
