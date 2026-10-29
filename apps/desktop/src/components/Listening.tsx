/** Small animated "sound bars", for listening/recording states. */
export function Listening({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex h-3.5 items-end gap-[3px] ${className}`} aria-hidden>
      {[0, 0.2, 0.4, 0.1].map((delay, i) => (
        <span
          key={i}
          className="h-full w-[3px] origin-bottom animate-bar rounded-full bg-current"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  );
}
