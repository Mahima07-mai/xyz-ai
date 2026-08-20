import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useChat } from "../hooks/useChat";
import { useLanguages } from "../hooks/useLanguages";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";
import { roleMeta } from "../lib/roles";
import AvatarWidget from "./AvatarWidget";
import ChatMessage from "./ChatMessage";
import EscalationPanel from "./EscalationPanel";

/**
 * The ONE chat widget every portal renders (StudentPortal, ParentPortal,
 * StaffPortal, ManagementPortal) -- per the project plan's Day 3
 * afternoon task: "Build/skin the React chat UI for all 4 portals
 * sharing one chat widget component." Portals only pass in which role
 * they're for; all request/response, history, reset, and escalation
 * logic lives here and in useChat, once.
 *
 * Day 4 morning adds the voice channel's input half here: a mic button
 * (useSpeechRecognition, Web Speech API) plus a language picker
 * (useLanguages, backed by the GET /languages endpoint) so a
 * transcribed utterance in any offered language is sent through this
 * exact same sendMessage() call a typed message would use -- per the
 * plan's "multi-channel parity" requirement, there is no separate voice
 * code path into the backend, only a different way of filling `draft`.
 *
 * Day 4 afternoon adds the output half: TTS (useSpeechSynthesis) reads
 * new assistant replies aloud, and AvatarWidget's mouth is driven by
 * that same utterance's word-boundary events, so voice output and the
 * avatar are one connected flow, not two independent features. Both
 * are pure additions on top of the existing `messages` state -- if the
 * browser doesn't support speechSynthesis, or the user turns voice
 * replies off, chat (typed or spoken-in) keeps working exactly as
 * before, per the plan's graceful-degradation requirement (section
 * 1.9): "if avatar/voice infrastructure fails or is unavailable, chat
 * must keep working."
 */
export default function ChatWidget({ role }) {
  const { session } = useAuth();
  const { messages, pending, error, sendMessage, resetConversation } = useChat();
  const { languages, fluentLanguages } = useLanguages();
  const meta = roleMeta(role);
  const [draft, setDraft] = useState("");
  const [escalationRefresh, setEscalationRefresh] = useState(0);
  const [showEscalations, setShowEscalations] = useState(false);
  // Which language to listen for. Defaults to English; the picker only
  // changes the STT locale (recognition.lang) and, on the output side,
  // the TTS voice/locale for spoken replies -- it never restricts what
  // the assistant will reply in, since the persona already detects and
  // mirrors the language of whatever text it receives (Day 3
  // _LANGUAGE_RULES in personas.py).
  const [voiceLang, setVoiceLang] = useState("en");
  // Voice OUTPUT (TTS + avatar mouth) is a separate on/off switch from
  // voice INPUT (the mic) -- someone may want to speak their questions
  // but still read replies, or vice versa. Defaults on; flipped off
  // automatically the first time speechSynthesis turns out to be
  // unsupported (see the effect below).
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(true);
  const [mouthOpen, setMouthOpen] = useState(false);
  const scrollRef = useRef(null);
  const lastSpokenMessageIdRef = useRef(null);
  const mouthTimerRef = useRef(null);

  const activeLocale = languages.find((l) => l.code === voiceLang)?.locale || "en-IN";

  const handleSend = async (text) => {
    const toSend = text ?? draft;
    if (!toSend.trim()) return;
    setDraft("");
    await sendMessage(toSend);
    // A turn may have just created/updated an escalation -- refresh the
    // panel so its "true status" stays in lockstep with what the
    // assistant just said (see EscalationPanel's docstring).
    setEscalationRefresh((n) => n + 1);
  };

  const {
    supported: micSupported,
    listening,
    interimTranscript,
    error: micError,
    start: startListening,
    stop: stopListening,
  } = useSpeechRecognition({
    lang: activeLocale,
    // A final transcript is sent immediately, same as pressing "Send"
    // on typed text -- per the plan's edge case "Noisy audio / failed
    // speech recognition -> ask the user to repeat", the hook itself
    // already withholds empty/garbled results, so anything that reaches
    // here is treated as a deliberate utterance.
    onResult: (finalText) => handleSend(finalText),
  });

  const {
    supported: ttsSupported,
    speaking,
    error: ttsError,
    speak,
    cancel: cancelSpeech,
  } = useSpeechSynthesis();

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  // Read new assistant replies aloud and drive the avatar's mouth from
  // the same utterance's boundary events. Guarded by
  // lastSpokenMessageIdRef so re-renders (or switching portals and
  // back) never re-speak a reply that was already read out once.
  useEffect(() => {
    if (!voiceOutputEnabled || !ttsSupported) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return;
    if (lastSpokenMessageIdRef.current === last.id) return;
    lastSpokenMessageIdRef.current = last.id;

    speak(last.content, activeLocale, {
      onBoundary: () => {
        // Flap the mouth open on each word boundary, then close it
        // shortly after -- a simple, real-signal-driven approximation
        // of a viseme per the plan's "simple 2D lip-synced avatar"
        // scope (section 1.7), rather than phoneme-accurate lip-sync.
        setMouthOpen(true);
        clearTimeout(mouthTimerRef.current);
        mouthTimerRef.current = setTimeout(() => setMouthOpen(false), 140);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, voiceOutputEnabled, ttsSupported, activeLocale]);

  // Close the mouth once speech actually ends (covers the tail end
  // after the last boundary event, and interruption via cancelSpeech).
  useEffect(() => {
    if (!speaking) {
      clearTimeout(mouthTimerRef.current);
      setMouthOpen(false);
    }
  }, [speaking]);

  const toggleMic = () => {
    if (listening) {
      stopListening();
      return;
    }
    // Don't let a spoken reply and the mic talk over each other -- per
    // the plan's multi-channel-parity spirit, voice input should feel
    // like a real conversational turn-take, not two audio streams at
    // once.
    cancelSpeech();
    startListening();
  };

  const onSubmit = (e) => {
    e.preventDefault();
    handleSend();
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="chalkboard flex h-[68vh] flex-col rounded-2xl shadow-chalk">
        {/* Header strip */}
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <p className="font-display text-base font-semibold text-chalk-25">XYZ AI</p>
            <p className="text-xs text-chalk-100/60">
              Speaking with you as <span className="text-marigold-400">{meta.label}</span>
              {session?.name ? ` · ${session.name}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {micSupported && (
              <select
                value={voiceLang}
                onChange={(e) => setVoiceLang(e.target.value)}
                disabled={listening}
                title="Language for voice input (speech-to-text) and spoken replies"
                className="rounded-lg bg-white/5 px-2 py-1.5 font-mono text-[11px] uppercase tracking-wide text-chalk-100/80 ring-1 ring-white/15 hover:bg-white/10 disabled:opacity-40"
              >
                {languages.map((l) => (
                  <option key={l.code} value={l.code} className="text-ink-900">
                    {l.name}
                    {l.fluent ? "" : " (English fallback)"}
                  </option>
                ))}
              </select>
            )}
            {ttsSupported && (
              <button
                type="button"
                onClick={() => {
                  if (voiceOutputEnabled) cancelSpeech();
                  setVoiceOutputEnabled((v) => !v);
                }}
                aria-pressed={voiceOutputEnabled}
                title={voiceOutputEnabled ? "Turn off spoken replies" : "Turn on spoken replies"}
                className={`rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide ring-1 transition ${
                  voiceOutputEnabled
                    ? "bg-marigold-400/15 text-marigold-400 ring-marigold-400/40"
                    : "text-chalk-100/80 ring-white/15 hover:bg-white/5"
                }`}
              >
                {voiceOutputEnabled ? "Voice: on" : "Voice: off"}
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowEscalations((v) => !v)}
              className="rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-chalk-100/80 ring-1 ring-white/15 hover:bg-white/5 lg:hidden"
            >
              Escalations
            </button>
            <button
              type="button"
              onClick={resetConversation}
              className="rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide text-chalk-100/80 ring-1 ring-white/15 hover:bg-white/5"
            >
              Reset chat
            </button>
          </div>
        </div>

        {/* Transcript */}
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <p className="max-w-xs text-sm text-chalk-100/70">
                Try: <span className="text-marigold-400">&ldquo;{meta.examplePrompt}&rdquo;</span>
              </p>
            </div>
          )}
          {messages.map((m) => (
            <ChatMessage key={m.id} role={m.role} content={m.content} at={m.at} />
          ))}
          {pending && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-tl-sm bg-chalk-900/60 px-4 py-2.5 text-chalk-100/60 ring-1 ring-white/5">
                <span className="inline-flex gap-1">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-chalk-100/60 [animation-delay:-0.2s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-chalk-100/60 [animation-delay:-0.1s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-chalk-100/60" />
                </span>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mx-5 mb-2 rounded-lg bg-rust-500/15 px-3 py-2 text-xs text-rust-400 ring-1 ring-rust-500/30">
            {error}
          </div>
        )}

        {micError && (
          <div className="mx-5 mb-2 rounded-lg bg-rust-500/15 px-3 py-2 text-xs text-rust-400 ring-1 ring-rust-500/30">
            {micError}
          </div>
        )}

        {ttsError && (
          <div className="mx-5 mb-2 rounded-lg bg-rust-500/15 px-3 py-2 text-xs text-rust-400 ring-1 ring-rust-500/30">
            {ttsError}
          </div>
        )}

        {listening && (
          <div className="mx-5 mb-2 flex items-center gap-2 rounded-lg bg-marigold-400/10 px-3 py-2 text-xs text-marigold-400 ring-1 ring-marigold-400/30">
            <span className="h-2 w-2 animate-pulse rounded-full bg-marigold-400" />
            Listening{interimTranscript ? `: “${interimTranscript}”` : "…"}
          </div>
        )}

        {/* Quick actions */}
        <div className="flex flex-wrap gap-2 px-5 pb-3">
          {meta.quickActions.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => handleSend(q)}
              disabled={pending}
              className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-chalk-100/80 ring-1 ring-white/10 transition hover:bg-white/10 disabled:opacity-40"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Composer */}
        <form onSubmit={onSubmit} className="flex items-center gap-2 border-t border-white/10 px-4 py-3">
          {micSupported && (
            <button
              type="button"
              onClick={toggleMic}
              disabled={pending}
              title={listening ? "Stop listening" : "Speak your message"}
              aria-pressed={listening}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 transition disabled:cursor-not-allowed disabled:opacity-40 ${
                listening
                  ? "animate-pulse bg-rust-500 text-white ring-rust-500"
                  : "bg-white/5 text-chalk-100/80 ring-white/10 hover:bg-white/10"
              }`}
            >
              {/* Simple inline mic glyph -- no icon library dependency, per
                  the plan's "no new frameworks/technologies" constraint. */}
              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
              </svg>
            </button>
          )}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Ask XYZ AI, in ${fluentLanguages.map((l) => l.name).join(", ")}…`}
            className="flex-1 rounded-xl bg-white/5 px-4 py-2.5 text-sm text-chalk-25 placeholder:text-chalk-100/40 ring-1 ring-white/10 focus:outline-none focus:ring-2 focus:ring-marigold-400"
            disabled={pending || listening}
          />
          <button
            type="submit"
            disabled={pending || listening || !draft.trim()}
            className="rounded-xl bg-marigold-400 px-4 py-2.5 text-sm font-semibold text-ink-900 transition hover:bg-marigold-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>

      {/* Sidebar: avatar (Day 4 afternoon) above escalations -- persistent
          on desktop, toggled with the "Escalations" button on mobile
          alongside the escalation panel so small screens aren't forced
          to scroll past a static avatar to reach it. */}
      <aside
        className={`space-y-4 lg:block ${showEscalations ? "block" : "hidden"}`}
      >
        <div className="chalkboard rounded-2xl p-4 shadow-chalk">
          <AvatarWidget speaking={speaking} listening={listening} thinking={pending} mouthOpen={mouthOpen} />
        </div>
        <div className="rounded-2xl bg-parchment-50 p-4 ring-1 ring-chalk-200">
          <EscalationPanel refreshSignal={escalationRefresh} />
        </div>
      </aside>
    </div>
  );
}
