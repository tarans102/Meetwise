import { useEffect } from "react";
import { X } from "lucide-react";

export function Button({ variant = "ghost", size, className = "", ...props }) {
  const sizeClass = size === "sm" ? " btn-sm" : "";
  return <button className={`btn btn-${variant}${sizeClass} ${className}`} {...props} />;
}

export function Badge({ tone = "", children }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ""}`}>{children}</span>;
}

export function Field({ label, children, className = "" }) {
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="overlay"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

/* Used for destructive actions. Nothing is deleted until the user confirms. */
export function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel, busy }) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="muted">{message}</p>
    </Modal>
  );
}

export function Tabs({ items, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.value}
          role="tab"
          aria-selected={value === item.value}
          className="tab"
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {item.count != null && <span className="muted"> {item.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return <p className="muted small" role="status">{label}…</p>;
}
