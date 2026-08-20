import { useAuth } from "../context/AuthContext";
import RoleBadge from "./RoleBadge";

export default function Header({ meta }) {
  const { session, logout } = useAuth();

  return (
    <header className="register-rule border-b border-chalk-200/60 bg-parchment-50/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-chalk-800 font-display text-lg font-semibold text-marigold-400 shadow-chalk">
            X
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-ink-900">{meta.portalName}</h1>
            <p className="text-xs text-ink-400">{meta.tagline}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <RoleBadge label={meta.label} accent={meta.accent} />
          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium text-ink-900">{session?.name}</p>
            <p className="font-mono text-[11px] text-ink-400">
              {meta.pkField}={session?.id}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-ink-600 ring-1 ring-chalk-200 hover:bg-white"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
