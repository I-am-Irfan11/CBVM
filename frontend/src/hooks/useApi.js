import { useEffect, useState } from "react";
import { api } from "../services/api";

export function useApi(path, revision) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  useEffect(() => {
    if (!path) {
      setState({ data: null, error: "", loading: false });
      return;
    }
    const controller = new AbortController();
    setState((old) => ({
      data: old.path === path ? old.data : null,
      path,
      error: "",
      loading: true,
    }));
    api(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ path, data, error: "", loading: false });
      })
      .catch((error) => {
        if (error.name !== "AbortError")
          setState({ path, data: null, error: error.message, loading: false });
      });
    return () => controller.abort();
  }, [path, revision]);
  return state.path === path
    ? state
    : { data: null, error: "", loading: Boolean(path) };
}
