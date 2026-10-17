export function Loading({ label = "Loading…" }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function ErrorAlert({ error, title }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      {title && <strong>{title}: </strong>}
      {error.message || String(error)}
      {error.details?.field && <span> (field: {String(error.details.field)})</span>}
      {error.requestId && <span className="ref">Reference: {error.requestId}</span>}
    </div>
  );
}

export function Alert({ tone = "info", children }) {
  if (!children) return null;
  return (
    <div className={`alert alert-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

// Renders loading / error / empty states for a useApi() result, or children.
export function AsyncBlock({ state, empty, isEmpty, children, loadingLabel }) {
  if (state.loading && !state.data) return <Loading label={loadingLabel} />;
  if (state.error) return <ErrorAlert error={state.error} />;
  if (!state.data) return null;
  if (isEmpty?.(state.data)) return empty;
  return children(state.data);
}
