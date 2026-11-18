export type Credentials = { session_id: string; token: string };
export type Message = {
  id: string;
  player: string;
  text: string;
  at: number;
  round: number;
};
export type Result = {
  round: number;
  counts: Record<string, number>;
  abstentions: number;
  winner?: string;
  tied?: string[];
  rule?: string;
};
export type State = {
  type: "state";
  session_id: string;
  you: string;
  players: string[];
  phase:
    "waiting" | "discussion" | "voting" | "feedback" | "complete" | "aborted";
  round: number;
  rounds: number;
  deadline: number;
  server_time: number;
  phase_started: number;
  discussion_seconds: number;
  messages: Message[];
  your_vote: string | null;
  results: Result[];
  winner: string | null;
  abort_reason: string | null;
};
