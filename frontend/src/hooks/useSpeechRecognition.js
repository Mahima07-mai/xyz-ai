import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Day 4 morning -- Voice channel, Speech-to-Text half.
 *
 * Per the project plan (section 2.3 tech stack table and section 3's
 * Day 4 roadmap: "Integrate STT (Web Speech API first, for speed) so
 * spoken input reaches the same chat pipeline"), this uses the
 * browser-native Web Speech API (SpeechRecognition /
 * webkitSpeechRecognition) rather than standing up a Whisper API
 * integration. That is the deliberate "faster path chosen for a 5-day
 * build" from the tech-stack table's footnote -- Whisper API remains
 * the documented upgrade path if time allows, and nothing about this
 * hook's interface would need to change for the ChatWidget if that
 * swap happens later (start/stop/onResult stay the same shape).
 *
 * Crucially, this hook does NOT talk to the backend at all: it only
 * turns speech into text locally in the browser. The resulting text is
 * handed to the caller via onResult, which ChatWidget feeds into the
 * exact same sendMessage() -> POST /chat flow typed messages already
 * use (project plan section 1.5: "Multi-channel parity ... the same
 * underlying logic must be reachable through typed chat [and] spoken
 * voice"). There is no separate "voice intent" pipeline to keep in
 * sync with the chat one.
 */
export function useSpeechRecognition({ lang = "en-IN", onResult } = {}) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState(null);
  const recognitionRef = useRef(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  useEffect(() => {
    // Chrome/Edge expose this as the vendor-prefixed
    // webkitSpeechRecognition; only Chromium-based browsers reliably
    // support the Indian-language locales this project needs, which is
    // fine for a demo but is exactly the kind of "technically possible"
    // caveat the project plan calls out for voice/avatar (section 1.7)
    // -- so this hook fails open to `supported: false` rather than
    // throwing, and ChatWidget hides the mic button when that happens.
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    setSupported(Boolean(SpeechRecognition));
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Speech recognition isn't supported in this browser. Try typing instead, or use Chrome.");
      return;
    }

    setError(null);
    setInterimTranscript("");

    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true);

    recognition.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        } else {
          interim += transcript;
        }
      }
      if (interim) setInterimTranscript(interim);
      if (final) {
        setInterimTranscript("");
        // Edge case from the project plan (section 1.8): "Noisy audio /
        // failed speech recognition -> assistant should ask the user to
        // repeat rather than acting on a garbled transcript." We can't
        // detect audio quality from here, but we do refuse to fire
        // onResult with an empty/whitespace-only final transcript --
        // that scenario (recognition ran, heard nothing usable) is the
        // most common "garbled" case in practice, and it is better
        // handled by simply not sending anything than by sending blank
        // text into the chat pipeline.
        const trimmed = final.trim();
        if (trimmed) onResultRef.current?.(trimmed);
      }
    };

    recognition.onerror = (event) => {
      const messages = {
        "not-allowed": "Microphone access was denied. Allow microphone access to use voice input.",
        "no-speech": "No speech was detected. Please try again and speak clearly.",
        "audio-capture": "No microphone was found. Check your device's audio input.",
        network: "A network error interrupted speech recognition. Please try again.",
      };
      setError(messages[event.error] || "Speech recognition failed. Please try again or type your message.");
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      setInterimTranscript("");
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [lang]);

  // Stop any in-flight recognition on unmount so a navigated-away
  // component doesn't keep the microphone open.
  useEffect(() => () => recognitionRef.current?.stop(), []);

  return { supported, listening, interimTranscript, error, start, stop };
}
