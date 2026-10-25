// The one module that talks to the backend WebSocket. Message types come from the
// generated Pydantic schemas (@scribely/schemas); never hand-write them here.
import type { WsProtocol } from "@scribely/schemas";

export type ClientMessage = WsProtocol["client"];
export type ServerMessage = WsProtocol["server"];
export type ConnectionState = "connecting" | "open" | "closed";

export const DEFAULT_WS_URL: string =
  import.meta.env.VITE_SCRIBELY_WS_URL ?? "ws://127.0.0.1:8765/ws";

const MIN_RETRY_MS = 500;
const MAX_RETRY_MS = 5000;

export class ScribelyClient {
  private socket: WebSocket | null = null;
  private retryMs = MIN_RETRY_MS;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(
    private readonly url: string,
    private readonly onMessage: (message: ServerMessage) => void,
    private readonly onConnection: (state: ConnectionState) => void,
  ) {}

  connect(): void {
    this.closed = false;
    this.onConnection("connecting");
    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.retryMs = MIN_RETRY_MS;
      this.onConnection("open");
    };
    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        this.onMessage(JSON.parse(event.data) as ServerMessage);
      } catch {
        console.warn("Ignoring malformed message from backend", event.data);
      }
    };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.onConnection("closed");
      if (!this.closed) this.scheduleReconnect();
    };
  }

  /** Returns false if the backend isn't connected. */
  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  close(): void {
    this.closed = true;
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.socket?.close();
    this.socket = null;
  }

  private scheduleReconnect(): void {
    this.retryTimer = setTimeout(() => this.connect(), this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, MAX_RETRY_MS);
  }
}
