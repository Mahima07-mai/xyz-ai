# XYZ AI — Frontend

React (Vite) + Tailwind CSS UI for the four XYZ AI portals, talking to
the FastAPI backend in [`../backend`](../backend). Nothing here decides
who can see what; every authorization decision happens server-side (see
`../backend/app/authz.py`). This app only carries the session token the
backend issues, and re-sends it on every request.

## What's here

- **Real role-scoped auth** (`src/portals/LoginPortal.jsx`,
  `src/context/AuthContext.jsx`): sign in with `role + identifier +
  password` against `POST /auth/login`, register a new account per role
  against `POST /auth/register/{role}` (teacher/student/parent/
  principal each have their own field set, matching
  `../backend/app/auth.py`'s pydantic models exactly), and reset a
  forgotten password via `POST /auth/forgot-password`. Identity is a
  role-scoped string (`"T001"`, a parent UUID, etc.), never a numeric
  `user_id` — `session.id` is kept as the raw string from the JWT's
  `sub` claim throughout the app.
- **One shared chat widget** (`src/components/ChatWidget.jsx`), used
  identically by all four portals. It calls `POST /chat` and
  `POST /chat/reset`, renders the transcript, offers role-specific quick
  actions (including the Phase 4 AI-analytics prompts — teaching
  insights, absentee patterns), and shows a live escalation-status panel
  (`src/components/EscalationPanel.jsx`, backed by `GET /escalations/mine`)
  so the "never claim success without genuine confirmation" guarantee is
  visibly demonstrable, not just asserted in chat. A voice channel (STT
  via `useSpeechRecognition`, TTS via `useSpeechSynthesis`) and a 2D
  avatar (`AvatarWidget.jsx`, now reacting to listening / **thinking** /
  speaking) sit alongside it; if either is unsupported, typed chat keeps
  working unmodified.
- **Per-role workspace panels** (`src/components/workspace/`), added
  for the flows that are genuinely form/table-shaped rather than a
  natural chat turn:
  - **Staff Portal** — `TeacherWorkspace.jsx`: the Flow C interactive
    attendance grid (default-present toggle buttons, bulk save to
    `POST /attendance/class`), the Flow D marks-entry grid (per-subject
    columns restricted to the subjects the signed-in teacher actually
    handles, with Total/Average/Grade computed client-side in real time
    and saved via `POST /marks/class`), a send-warning form, and the
    teacher's own inbox.
  - **Management Portal** — `PrincipalDashboard.jsx`: the Flow F
    class/section summary grid with metric cards, a subject-based
    teacher search, and student/teacher bio lookups.
  - **Student / Parent Portals** — a profile panel (own bio for
    students; a child-ID lookup for parents, since the linked child
    isn't part of a parent's JWT) plus a message-a-teacher form.

  These call the exact same authorized backend actions the chat tools
  do (`tools.py`) — they're a faster, table-shaped alternative path for
  bulk/structured entry, not a separate or looser one. A denied call
  (wrong class/section, wrong subject, etc.) surfaces as the same
  honest error text the backend returns.
- **Four thin portal pages** (`src/portals/{Student,Parent,Staff,Management}Portal.jsx`).
  Each is `PortalShell` (header + optional workspace + chat), 
  parameterized by role — there is deliberately no per-portal
  reimplementation to drift out of sync.
- **Client-side route guarding only** (`src/components/ProtectedRoute.jsx`) —
  a UX convenience that avoids showing a signed-in student the Principal
  portal, but not a security boundary: every request still carries that
  student's real JWT, so the backend would deny any out-of-scope tool
  call regardless of which URL was typed.

## Design system

A school-register visual language, distinct from the backend's
plumbing: **chalkboard** greens/near-black (`chalk-800`/`900`) for the
AI chat surface itself (with a faint chalk-dust texture — see
`.chalkboard` in `src/index.css`), **parchment** cream for the four
portal shells and workspace panels, **marigold** for the user's own
messages and primary actions, and **rust** reserved for denials/errors
— echoing an attendance register's ink colors rather than a generic
SaaS palette. Display type is Fraunces; body type is IBM Plex Sans
**plus its Devanagari and Tamil companion faces**, so non-English
replies (`../backend/app/language.py`) render in their native script
instead of falling back to a system font. `RoleBadge` doubles as the
"ID card stamp" signature element tying the four portals together
visually.

## Run it

```bash
# 1. Backend first (see ../backend: .env with OPENROUTER_API_KEY +
#    JWT_SECRET + DATABASE_URL, then `python -m app.seed_data`, then
#    `uvicorn app.main:app --reload --port 8000`).

# 2. Frontend
cp .env.example .env   # adjust VITE_API_BASE_URL if the backend isn't on :8000
npm install
npm run dev             # http://localhost:5173
```

Register an account for your role (or sign in with one of
`seed_data.py`'s seeded accounts — see its printed credentials, all
sharing the seed password), then use the portal's chat widget and
workspace panels together. E.g. as the Teacher demo account
(`teacher_id=T001`): type *"Mark Rahul absent today"* in chat, or open
the Attendance tab in the workspace panel above it and toggle the whole
class at once — both call the same authorized backend action.

## Notes / honest scope

- Voice/avatar support depends on the browser (Web Speech API is
  Chromium-reliable). If unsupported, the mic button and voice-output
  toggle simply don't render, and chat keeps working exactly as before.
- Only English, Hindi, Tamil, Telugu, Marathi, and Bengali are demoed
  with real conversational fluency (`../backend/app/language.py`); the
  language picker and composer placeholder reflect exactly that list
  rather than overclaiming all 11 target languages.
- The marks-entry grid starts blank rather than pre-filled: the backend
  currently exposes a bulk-*save* endpoint (`POST /marks/class`) but no
  bulk-*read* endpoint for previously entered marks, so this UI doesn't
  invent or guess at existing values. A `GET /marks/class` read endpoint
  would be a natural next backend addition to pre-fill this grid.
- There is no backend endpoint yet to mark a `teacher_communications`
  row as read, so the teacher inbox is read-only display for now (no
  "mark as read" action).
- `sessionStorage` (not `localStorage`) holds the session token,
  matching the token's own 2-hour expiry and clearing on tab close.
