import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Day 4 afternoon -- Voice channel, Text-to-Speech half.
 *
 * Mirrors useSpeechRecognition.js's approach exactly, for the same
 * reason: the project plan's tech-stack table (section 2.3) lists
 * "TTS (Azure/ElevenLabs)" as the recommended option, but its own
 * footnote says "where two options are listed, the first is the faster
 * path chosen for a 5-day build; the second is the higher-quality
 * option worth swapping in only if time remains." The browser-native
 * Web Speech API TTS (SpeechSynthesisUtterance) is that faster path --
 * no new API key, no new backend dependency, and it reuses the exact
 * same "browser does the media work, backend never sees audio" shape
 * already established for STT. Swapping in Azure/ElevenLabs later would
 * only mean replacing the body of `speak()` with an API call that plays
 * back a returned audio blob; nothing about this hook's interface
 * (speak/cancel/speaking/onBoundary) would need to change upstream in
 * ChatWidget or AvatarWidget.
 *
 * `speak(text, locale, { onBoundary })` drives the avatar layer: most
 * desktop-Chrome-family browsers fire `boundary` events at each word as
 * the utterance plays, which AvatarWidget's mouth animation is timed
 * to (see ChatWidget.jsx) -- this is what makes the avatar "driven by
 * the TTS output" per the plan's Day 4 afternoon wording, rather than a
 * generic looping mouth animation unrelated to what's actually being
 * said.
 */
export function useSpeechSynthesis() {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState(null);
  const utteranceRef = useRef(null);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
  }, []);

  const pickVoice = useCallback((locale) => {
    // getVoices() can return an empty list on the very first call in
    // some browsers until the async 'voiceschanged' event fires; that's
    // a known Web Speech API quirk, not a bug here. Falling through to
    // undefined just means the browser's default voice is used instead
    // of a locale-matched one -- speech still plays, just possibly in
    // the wrong accent, which is an acceptable "technically possible"
    // degradation for a demo (project plan section 1.7) rather than a
    // failure.
    const voices = window.speechSynthesis.getVoices();
    return (
      voices.find((v) => v.lang === locale) ||
      voices.find((v) => v.lang?.toLowerCase().startsWith(locale.split("-")[0].toLowerCase())) ||
      null
    );
  }, []);

  const cancel = useCallback(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text, locale, { onBoundary } = {}) => {
      if (!supported || !text?.trim()) return;

      // Only one utterance should ever be in flight -- e.g. if a new
      // reply arrives while an older one is still being read out, or
      // the user starts the mic (see ChatWidget's toggleMic), the
      // previous utterance is cancelled rather than queued/overlapped.
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = locale;
      const voice = pickVoice(locale);
      if (voice) utterance.voice = voice;

      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = (event) => {
        // "interrupted"/"canceled" fire on every deliberate cancel()
        // call above -- that's expected control flow, not a real
        // failure, so only surface an error for anything else. Voice
        // playback failing should never block or hide the text reply
        // that's already on screen (graceful degradation, section 1.9).
        if (event.error !== "interrupted" && event.error !== "canceled") {
          setError("Voice playback failed; the reply is still shown as text above.");
        }
        setSpeaking(false);
      };
      utterance.onboundary = (event) => onBoundary?.(event);

      utteranceRef.current = utterance;
      setError(null);
      window.speechSynthesis.speak(utterance);
    },
    [supported, pickVoice]
  );

  // Stop any in-flight speech on unmount so a navigated-away component
  // doesn't keep talking in the background.
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  return { supported, speaking, error, speak, cancel };
}
