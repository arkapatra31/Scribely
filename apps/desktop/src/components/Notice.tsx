import { AnimatePresence, motion } from "framer-motion";
import { KeyRound, TriangleAlert, WifiOff, X } from "lucide-react";
import type { ReactNode } from "react";

const ICONS = { warn: TriangleAlert, offline: WifiOff, key: KeyRound };

interface Props {
  show: boolean;
  kind: keyof typeof ICONS;
  children: ReactNode;
  action?: { label: string; onClick: () => void };
  onDismiss?: () => void;
}

/** A slim, calm notice at the top of the main pane. */
export function Notice({ show, kind, children, action, onDismiss }: Props) {
  const Icon = ICONS[kind];
  const tone =
    kind === "key"
      ? "bg-accent-soft text-accent-ink border-accent/20"
      : "bg-warn-soft text-warn border-warn/20";
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          role={kind === "key" ? "status" : "alert"}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.2 }}
          className="overflow-hidden px-6 pt-4"
        >
          <div className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm ${tone}`}>
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            <p className="min-w-0 flex-1">{children}</p>
            {action && (
              <button
                type="button"
                onClick={action.onClick}
                className="shrink-0 rounded-full bg-accent px-3 py-1 text-xs font-medium text-white transition hover:bg-accent-strong dark:text-paper"
              >
                {action.label}
              </button>
            )}
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss"
                className="shrink-0 rounded-md p-0.5 opacity-60 transition hover:opacity-100"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
