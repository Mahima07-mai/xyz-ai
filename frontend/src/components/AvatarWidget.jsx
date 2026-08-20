/**
 * Avatar layer -- a simple 2D, vector (inline SVG) avatar with three
 * states driven by real signals rather than a generic idle loop:
 *
 *   - `thinking` reflects the real in-flight /chat request (ChatWidget's
 *     `pending` from useChat) -- the "processing" state the avatar spec
 *     calls for, alongside listening/speaking.
 *   - `mouthOpen` is toggled by ChatWidget in direct response to the
 *     TTS utterance's `boundary` events (see useSpeechSynthesis.js) --
 *     so the mouth is driven by the TTS output, not a timer.
 *   - `listening` reflects the real STT recognition state from
 *     useSpeechRecognition.js.
 *
 * Precedence when more than one could apply: listening > thinking >
 * speaking > idle -- a user who starts talking while a reply is still
 * being read out should see the avatar switch to "listening"
 * immediately, not stay stuck on "speaking".
 *
 * The idle eye-blink is the one purely decorative animation (CSS
 * keyframes in index.css) -- it has no signal to be driven by; it just
 * keeps the avatar from looking like a static image when nothing else
 * is happening. The outer ring's rotating gradient while `thinking` is
 * also decorative (there's no finer-grained "progress" signal to drive
 * it from), but is scoped tightly to the actual pending window so it
 * never runs when nothing is happening.
 *
 * Consumed by ChatWidget.jsx, which owns the "is voice/avatar output
 * even supported/enabled" decision -- this component only ever renders
 * whatever state it's handed and never talks to speechSynthesis or
 * SpeechRecognition itself.
 */
export default function AvatarWidget({ speaking = false, listening = false, thinking = false, mouthOpen = false, label }) {
  const state = listening ? "listening" : thinking ? "thinking" : speaking ? "speaking" : "idle";
  const ringColor = {
    listening: "stroke-rust-500",
    thinking: "stroke-marigold-400/70",
    speaking: "stroke-marigold-400",
    idle: "stroke-white/15",
  }[state];
  const statusText =
    label ??
    { listening: "Listening…", thinking: "Thinking…", speaking: "Speaking…", idle: "XYZ AI" }[state];

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-24 w-24 lg:h-32 lg:w-32">
        {thinking && (
          <div
            className="absolute inset-0 animate-spin rounded-full opacity-70 [animation-duration:1.6s]"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 0%, rgba(232,185,74,0.55) 35%, transparent 55%)",
            }}
          />
        )}
        <svg
          viewBox="0 0 200 200"
          className="relative h-full w-full"
          role="img"
          aria-label={`XYZ AI avatar, currently ${state}`}
        >
          {/* Face */}
          <circle cx="100" cy="100" r="90" className={`fill-chalk-900 stroke-[6] transition-colors duration-300 ${ringColor}`} />

          {/* Eyes -- purely decorative idle blink, see index.css .avatar-blink.
              Suppressed while thinking so the "processing" cue reads clearly
              rather than competing with a blink. */}
          <g className={thinking ? "" : "avatar-blink"}>
            {thinking ? (
              <>
                <rect x="58" y="83" width="20" height="6" rx="3" className="fill-marigold-400/80" />
                <rect x="122" y="83" width="20" height="6" rx="3" className="fill-marigold-400/80" />
              </>
            ) : (
              <>
                <ellipse cx="68" cy="86" rx="10" ry="13" className="fill-chalk-25" />
                <ellipse cx="132" cy="86" rx="10" ry="13" className="fill-chalk-25" />
              </>
            )}
          </g>

          {/* Eyebrows -- shift up slightly while listening, a small "attentive" cue */}
          <g className={`transition-transform duration-200 ${listening ? "-translate-y-1.5" : ""}`}>
            <rect x="54" y="62" width="28" height="6" rx="3" className="fill-chalk-100/70" />
            <rect x="118" y="62" width="28" height="6" rx="3" className="fill-chalk-100/70" />
          </g>

          {/* Mouth -- the one part actually driven by the TTS boundary
              events, via the `mouthOpen` prop (see ChatWidget.jsx), except
              while thinking, when it shows a simple three-dot "typing"
              cue instead. Two simple visemes for speech: an open ellipse
              vs. a closed flat bar -- deliberately not phoneme-accurate
              lip-sync, a believable open/close flap timed to word
              boundaries as they arrive. */}
          {thinking ? (
            <g className="fill-marigold-400">
              <circle cx="82" cy="138" r="5" className="animate-bounce [animation-delay:-0.2s]" />
              <circle cx="100" cy="138" r="5" className="animate-bounce [animation-delay:-0.1s]" />
              <circle cx="118" cy="138" r="5" className="animate-bounce" />
            </g>
          ) : speaking && mouthOpen ? (
            <ellipse cx="100" cy="138" rx="24" ry="14" className="fill-marigold-400 transition-all duration-100" />
          ) : (
            <rect x="76" y="134" width="48" height="8" rx="4" className="fill-marigold-400 transition-all duration-100" />
          )}
        </svg>
      </div>
      <p className="font-mono text-[10px] uppercase tracking-wide text-chalk-100/60">{statusText}</p>
    </div>
  );
}
