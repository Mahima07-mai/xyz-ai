import { useEffect, useState } from "react";
import { api } from "../api/client";

/**
 * Day 4: fetches the language catalog from GET /languages so the
 * frontend never re-declares which languages are "fluent" vs. just
 * offered for speech input -- backend/app/language.py is the single
 * source of truth (see that module's docstring). Falls back to the
 * Day 3 static list if the backend is briefly unreachable, so the
 * chat widget still renders something sensible instead of an empty
 * picker.
 *
 * Each entry: { code, name, locale, fluent }.
 *   code   - two-letter code the LLM/persona rules use (e.g. "hi")
 *   name   - display name (e.g. "Hindi")
 *   locale - BCP-47 tag for the browser SpeechRecognition API (e.g. "hi-IN")
 *   fluent - whether the assistant can hold a real conversation in it today
 */
const FALLBACK_LANGUAGES = [
  { code: "en", name: "English", locale: "en-IN", fluent: true },
  { code: "hi", name: "Hindi", locale: "hi-IN", fluent: true },
  { code: "ta", name: "Tamil", locale: "ta-IN", fluent: true },
  { code: "te", name: "Telugu", locale: "te-IN", fluent: true },
  { code: "mr", name: "Marathi", locale: "mr-IN", fluent: true },
  { code: "bn", name: "Bengali", locale: "bn-IN", fluent: true },
];

export function useLanguages() {
  const [languages, setLanguages] = useState(FALLBACK_LANGUAGES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .languages()
      .then((data) => {
        if (!cancelled && data?.languages?.length) {
          setLanguages(data.languages);
        }
      })
      .catch(() => {
        // Backend unreachable -- keep the fallback list rather than
        // breaking the language picker or the voice input entirely.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fluentLanguages = languages.filter((l) => l.fluent);

  return { languages, fluentLanguages, loading };
}
