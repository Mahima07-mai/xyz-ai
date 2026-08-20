function formatTime(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * One turn in the transcript. Assistant replies render on the chalkboard
 * surface in chalk-white; the user's own messages render as a marigold
 * "written-in" note pinned to the right, echoing the register-book
 * signature without literally drawing a form.
 */
export default function ChatMessage({ role, content, at }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[80%] rounded-2xl rounded-tr-sm bg-marigold-400 px-4 py-2.5 text-ink-900 shadow-sm"
            : "max-w-[80%] rounded-2xl rounded-tl-sm bg-chalk-900/60 px-4 py-2.5 text-chalk-25 shadow-sm ring-1 ring-white/5"
        }
      >
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{content}</p>
        <p
          className={`mt-1 font-mono text-[10px] uppercase tracking-wide ${
            isUser ? "text-ink-900/50" : "text-chalk-100/40"
          }`}
        >
          {isUser ? "You" : "XYZ AI"} · {formatTime(at)}
        </p>
      </div>
    </div>
  );
}
