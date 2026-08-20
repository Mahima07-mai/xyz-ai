/**
 * Shared card wrapper for every role's structured (non-chat) workspace
 * panel -- Flow C/D/E/F. Kept as one tiny component so all the grids/
 * dashboards below share the same surface styling as the rest of the
 * app (parchment card, chalk ring) instead of four slightly different
 * re-implementations.
 */
export default function Panel({ title, subtitle, children }) {
  return (
    <section className="rounded-2xl bg-parchment-50 p-5 shadow-chalk ring-1 ring-chalk-200/60">
      <div className="mb-4">
        <h2 className="font-display text-lg font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}
