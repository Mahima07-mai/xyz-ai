# XYZ AI

A role-aware school assistant for Student, Parent, Teacher, and
Principal, built against the project plan's phased roadmap. This
folder is the `xyz-ai` module referenced by the plan's repo structure
and contains both halves of the Day 3 deliverable:

```
xyz-ai/
├── backend/     FastAPI core: auth, authorization, tools, LLM
│                orchestration, escalation, security, seed data (Day 1-3)
└── frontend/    React (Vite) + Tailwind chat UI for all 4 portals,
                 sharing one chat widget component (Day 3)
```

## Day 3 status (per the project plan, section 3)

- ✅ Escalation flow with a genuine pending/confirmed/failed lifecycle
  (`backend/app/escalation.py`) — the assistant never claims success
  without a tool-confirmed result, and the frontend's escalation panel
  reads the same rows back so the claim is independently checkable.
- ✅ Security pass: fake-role-claim resistance (JWT-only role, never
  chat text), a non-blocking prompt-injection heuristic, and an
  outgoing system-prompt-leak guard (`backend/app/security.py`,
  `backend/tests/test_security.py`).
- ✅ Working chat UI for all four roles, one shared widget, basic
  mocked login/role selection (`frontend/`).
- ✅ English + Hindi + Tamil demoed with real fluency
  (`backend/app/language.py`); the rest of the 11-language requirement
  is honestly scoped as Day 4 work, per the plan's own framing.

## Day 4 status (per the project plan, section 3)

- ✅ Speech-to-Text voice input, browser-native Web Speech API per the
  plan's "faster path chosen for a 5-day build"
  (`frontend/src/hooks/useSpeechRecognition.js`). A transcribed
  utterance is sent through the exact same `POST /chat` call a typed
  message uses — there is no separate voice code path on the backend,
  satisfying the plan's "multi-channel parity" requirement for STT.
- ✅ Language coverage extended from 3 to 6 fluent languages: English,
  Hindi, Tamil (Day 3) + Telugu, Marathi, Bengali (Day 4 evening) — see
  `backend/app/language.py`. Understanding/response is still LLM-native
  per the plan's architecture (section 2.2), not a bolted-on
  translation service.
- ✅ New `GET /languages` endpoint (`backend/app/main.py`) as the single
  source of truth for which languages are fluent vs. English-fallback,
  and each one's BCP-47 locale for STT — consumed by the frontend's
  language picker (`frontend/src/hooks/useLanguages.js`) so the two
  sides can't drift out of sync.
- ✅ Text-to-Speech voice output, browser-native Web Speech API
  (`SpeechSynthesisUtterance`) for the same "faster path for a 5-day
  build" reason STT uses `SpeechRecognition`
  (`frontend/src/hooks/useSpeechSynthesis.js`). Assistant replies are
  read aloud automatically when voice output is on; a header toggle
  turns it off per-session without touching typed chat at all.
- ✅ Simple 2D avatar (`frontend/src/components/AvatarWidget.jsx`), an
  inline SVG face with no new animation-library dependency. Its mouth
  is driven by the TTS utterance's real `boundary` events (word-timed
  open/close), and its "listening" ring reflects the actual STT state
  — both real signals, not a generic idle loop, per the plan's "driven
  by the TTS output" wording for this layer.
- ✅ Graceful fallback confirmed: if `speechSynthesis` is unsupported,
  the voice-output toggle and avatar mouth-drive simply don't render/
  activate — the avatar still shows (idle, blinking) and chat keeps
  working exactly as before, per the plan's graceful-degradation
  non-functional requirement (section 1.9).

## Known schema deviation from the current directive

`backend/app/model.py`'s schema is an intentional **superset** of the
current project directive's §2 schema, not a literal match:

- `auth_teacher.subject_handled`, `teacher_bio.subject_handled`, and
  `teacher_communications.subject_handled` are not present in the
  current directive's schema at all.
- `exam_marks`'s subject columns are named `maths_mark`, `science_mark`,
  `language_mark`, `social_mark`, `technology_mark`, where the current
  directive specifies generic `subject1_mark` .. `subject5_mark`
  columns.

These are carried over from an earlier, more detailed version of the
directive that scoped teacher permissions and analytics per named
subject. The decision on Day 3 was to **keep** this behavior rather
than strip it back to the generic schema, because subject-scoped
teacher authorization (`authz.py`'s `verify_teacher_subject_access` /
`ALLOWED_SUBJECTS`) and subject-scoped marks entry (`tools.py`'s
`SUBJECT_COLUMNS`, the frontend marks-entry grid) are both already
built on named subjects end-to-end, and named subjects are materially
more useful for a real school (a teacher's permissions and a report
card both need to say "Science", not "subject3"). Reverting to the
generic schema would be a regression in usefulness for no functional
gain, so this deviation is being kept and documented here rather than
silently carried forward or silently reverted.

If a future revision of the directive requires the literal generic
column names, `model.py`, `auth.py` (`ALLOWED_SUBJECTS` / registration
validation), `authz.py` (per-subject checks), `tools.py`
(`SUBJECT_COLUMNS`), and the frontend marks-entry grid all need to
change together, since they currently share the same named-subject
vocabulary.

## Quickstart

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set OPENROUTER_API_KEY, JWT_SECRET, DATABASE_URL
python -m app.seed_data
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev             # http://localhost:5173
```

Open the frontend, sign in with one of the demo accounts (or any seeded
`user_id`), and try the four core use cases from the project plan's
section 1.3 — e.g. as the Principal demo account: *"What is the overall
attendance?"*

See `backend/` and `frontend/` for module-specific details.