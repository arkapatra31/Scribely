import { motion, useReducedMotion } from "framer-motion";

export default function App() {
  const reduceMotion = useReducedMotion();

  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-50 text-stone-800 dark:bg-stone-950 dark:text-stone-100">
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="text-center"
      >
        <h1 className="text-3xl font-semibold tracking-tight">Scribely</h1>
        <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
          Listen, learn, and let Scribely take the notes.
        </p>
      </motion.div>
    </main>
  );
}
