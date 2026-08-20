const ACCENT_CLASSES = {
  chalk: "bg-chalk-100 text-chalk-800 ring-chalk-200",
  marigold: "bg-marigold-400/20 text-marigold-600 ring-marigold-400/40",
  rust: "bg-rust-400/15 text-rust-600 ring-rust-400/40",
  ink: "bg-ink-900/10 text-ink-900 ring-ink-900/20",
};

/**
 * Small "ID card stamp" badge naming the verified role, always rendered
 * from the session (see AuthContext) -- never from anything typed into
 * chat, which is the same rule the backend's authz layer enforces
 * server-side. Purely a visual echo of that rule, not an enforcement of it.
 */
export default function RoleBadge({ label, accent = "chalk", className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-xs font-medium uppercase tracking-wide ring-1 ${ACCENT_CLASSES[accent]} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
