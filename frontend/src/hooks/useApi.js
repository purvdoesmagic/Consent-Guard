import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api.js";

// Loads a GET endpoint and exposes { data, error, loading, reload }.
// Pass null as the path to skip loading.
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const controller = useRef(null);

  const reload = useCallback(async () => {
    if (!path) return;
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await api(path, { signal: ctrl.signal });
      if (!ctrl.signal.aborted) setState({ data, error: null, loading: false });
    } catch (error) {
      if (error.name !== "AbortError") setState({ data: null, error, loading: false });
    }
  }, [path]);

  useEffect(() => {
    reload();
    return () => controller.current?.abort();
  }, [reload]);

  return { ...state, reload };
}

// Wraps an async action with pending/error/success state for forms and buttons.
export function useAction() {
  const [state, setState] = useState({ pending: false, error: null, success: null });
  const run = useCallback(async (fn, successMessage = null) => {
    setState({ pending: true, error: null, success: null });
    try {
      const result = await fn();
      setState({ pending: false, error: null, success: successMessage });
      return result;
    } catch (error) {
      setState({ pending: false, error, success: null });
      return undefined;
    }
  }, []);
  const reset = useCallback(() => setState({ pending: false, error: null, success: null }), []);
  return { ...state, run, reset };
}
