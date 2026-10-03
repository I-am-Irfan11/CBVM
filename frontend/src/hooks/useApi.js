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
    setState((old) => ({ ...old, error: "", loading: true }));
    api(path, { signal: controller.signal })
      .then((data) => setState({ data, error: "", loading: false }))
      .catch((error) => {
        if (error.name !== "AbortError")
          setState({ data: null, error: error.message, loading: false });
      });
    return () => controller.abort();
  }, [path, revision]);
  return state;
}
