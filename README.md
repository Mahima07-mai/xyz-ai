# XYZ AI — Human-Like AI School Assistant

A role-aware school assistant for **Student, Parent, Teacher, and
Principal**, built to the "Human-Like AI School Assistant" brief:
natural-language chat, voice + a 2D avatar, role-based personas,
mock-service escalation to a real person, multi-language support, and
authorization enforced in code rather than trusted to the LLM.

```
xyz-ai/
├── backend/     FastAPI: role-scoped auth, authorization, chat/tool
│                orchestration (OpenRouter), escalation, security
│                guards, seed data, tests
└── frontend/    React (Vite) + Tailwind chat UI for all 4 portals,
                 with voice input/output, a 2D avatar, and per-role
                 workspace panels alongside the shared chat widget
```

See **[REQUIREMENTS.md](./REQUIREMENTS.md)** for a full, honest,
requirement-by-requirement comparison against the original brief,
including two things that still need fixing (a hardcoded API key/JWT
secret, and a missing language). The summary below is the short
version.

## What's actually implemented

- **The four required use cases**, end-to-end, authorization-enforced:
  student views own attendance, parent views a linked child's
  attendance, teacher marks attendance for their own class, principal
  gets school-wide attendance analytics. (`backend/app/tools.py`)
- **Beyond the four examples**: exam marks entry/viewing, class failure
  reports, subject-performance insights, attendance-pattern analytics,
  teacher-by-subject lookup, student/teacher bio lookups, and a
  teacher-communications inbox (warnings to students, questions from
  parents) — all authorization-scoped the same way.
- **Escalation with a real lifecycle** — pending / confirmed / failed,
  read back from a row a mock service actually wrote, never asserted by
  the LLM (`backend/app/escalation.py`). The frontend's escalation
  panel reads the same rows, so the claim is independently checkable.
- **Role-based personas** — Student (friendly academic assistant),
  Parent (caring/patient support), Teacher (professional teaching
  assistant), Principal (professional management assistant), selected
  automatically from the verified JWT role, never from chat text
  (`backend/app/personas.py`).
- **Voice + avatar** — browser-native Speech-to-Text and Text-to-Speech
  (Web Speech API), and a 2D SVG avatar whose mouth is driven by real
  TTS word-boundary events and whose "listening" state reflects actual
  STT state. This is real-time and reactive, but it is **not**
  full facial-expression animation or true lip-sync — see
  REQUIREMENTS.md §3 for the honest scope.
- **6 of the 11 required languages fluently**: English, Hindi, Tamil,
  Telugu, Marathi, Bengali. Gujarati, Kannada, Malayalam, and Punjabi
  can be spoken to (STT) but fall back to English replies. **Urdu is
  currently missing** from the language list — see REQUIREMENTS.md §5.
- **Security enforced at the application layer, not the prompt layer**:
  role comes only from a verified JWT (`authz.py`, ~1,700 lines of
  per-resource scoping checks), a non-blocking prompt-injection
  heuristic flags suspicious input for audit, and an outgoing guard
  blocks any reply that looks like a leaked system prompt
  (`backend/app/security.py`). 21/21 tests pass
  (`backend/tests/test_security.py`).

## Known issue — fix before calling this done

`backend/app/config.py` currently falls back to a **real-looking
hardcoded OpenRouter API key and JWT secret** if no environment
variable is set, and the committed `backend/.env` has the same values
in plaintext. This directly contradicts the brief's "protect against
API-key/credential extraction" requirement. Rotate both values and see
REQUIREMENTS.md §7 for the fix. Don't deploy this as-is.

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

Open the frontend, sign in with a seeded demo account (see
`seed_data.py`'s printed credentials) or register a new one per role,
and try the four core use cases — e.g. as the Principal demo account:
*"What is the overall attendance?"*

Run the backend test suite:

```bash
cd backend
pytest -q
```

See `backend/` and `frontend/` for module-specific details, and
`REQUIREMENTS.md` for what's done vs. what's honestly still scoped down
or outright missing against the brief.