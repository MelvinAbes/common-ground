import { useEffect, useRef, useState } from "react";
import type { Credentials, State } from "./types";

const STORAGE_KEY = "common-ground-participant";
function stored(): Credentials | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
    return value &&
      typeof value.session_id === "string" &&
      typeof value.token === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}

export function useExperiment() {
  const [credentials, setCredentials] = useState<Credentials | null>(stored);
  const [state, setState] = useState<State | null>(null);
  const [connection, setConnection] = useState("offline");
  const [error, setError] = useState("");
  const [joining, setJoining] = useState(false);
  const [pending, setPending] = useState(false);
  const [acceptedMessage, setAcceptedMessage] = useState(0);
  const socket = useRef<WebSocket | null>(null);
  const pendingAction = useRef<Record<string, unknown> | null>(null);
  const offset = useRef(0);

  useEffect(() => {
    if (!credentials) return;
    const { session_id, token } = credentials;
    let disposed = false;
    let retry: ReturnType<typeof setTimeout>;
    let attempts = 0;
    function connect() {
      if (disposed) return;
      setConnection("connecting");
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${location.host}/api/ws/${session_id}`,
      );
      socket.current = ws;
      let authenticated = false;
      const active = () => !disposed && socket.current === ws;
      ws.onopen = () => {
        if (active()) ws.send(JSON.stringify({ token }));
      };
      ws.onmessage = (event) => {
        if (!active()) return;
        const data = JSON.parse(event.data);
        if (data.type === "state") {
          offset.current = data.server_time * 1000 - Date.now();
          // The server sends committed states in order on this connection.
          setState(data);
          setConnection("online");
          attempts = 0;
          if (!authenticated && pendingAction.current)
            ws.send(JSON.stringify(pendingAction.current));
          authenticated = true;
        } else if (data.type === "ack" || data.type === "error") {
          if (data.type === "error")
            setError(data.message || "Please try again.");
          if (pendingAction.current?.request_id === data.request_id) {
            if (
              data.type === "ack" &&
              pendingAction.current?.type === "message"
            ) {
              setAcceptedMessage((value) => value + 1);
            }
            pendingAction.current = null;
            setPending(false);
          }
        } else if (data.type === "fatal") {
          setError(data.message);
          setConnection("failed");
          disposed = true;
        }
      };
      ws.onclose = (event) => {
        if (!active()) return;
        if (event.code === 4001) {
          setError(
            "This participant is open in another tab. Return to that tab or join a new session.",
          );
          setConnection("failed");
          return;
        }
        setConnection("connecting");
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 8000));
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      socket.current?.close();
    };
  }, [credentials]);

  async function join() {
    setJoining(true);
    setError("");
    try {
      const response = await fetch("/api/join", { method: "POST" });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "Could not join the experiment.");
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      setCredentials(data);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not connect.");
    } finally {
      setJoining(false);
    }
  }

  function reset() {
    socket.current?.close();
    socket.current = null;
    sessionStorage.removeItem(STORAGE_KEY);
    pendingAction.current = null;
    setPending(false);
    setCredentials(null);
    setState(null);
    setError("");
    setConnection("offline");
  }

  function send(type: "message" | "vote", payload: Record<string, string>) {
    if (
      socket.current?.readyState !== WebSocket.OPEN ||
      connection !== "online" ||
      pendingAction.current
    )
      return;
    setError("");
    const command = {
      type,
      ...payload,
      round: state?.round,
      request_id: crypto.randomUUID(),
    };
    pendingAction.current = command;
    setPending(true);
    socket.current.send(JSON.stringify(command));
  }

  return {
    credentials,
    state,
    connection,
    error,
    joining,
    pending,
    acceptedMessage,
    offset,
    join,
    reset,
    send,
    clearError: () => setError(""),
  };
}
