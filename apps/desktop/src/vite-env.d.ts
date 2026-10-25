/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend WebSocket URL; defaults to ws://127.0.0.1:8765/ws. */
  readonly VITE_SCRIBELY_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
