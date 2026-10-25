import { AnimatePresence, motion } from "framer-motion";

interface Props {
  message: string | null;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          role="alert"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="overflow-hidden"
        >
          <div className="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
            <p className="flex-1">{message}</p>
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                className="shrink-0 text-amber-700 hover:text-amber-900 dark:text-amber-300"
                aria-label="Dismiss"
              >
                ✕
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
