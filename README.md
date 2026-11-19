# TravelMate AI

Agentic travel planner. React + Vite + Tailwind + Axios + React Router frontend, FastAPI + Pydantic backend,
GitHub Copilot SDK for the LLM, MongoDB for storage, LangChain + ChromaDB + Sentence Transformers for RAG.

## Run on Windows (PowerShell)

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then set MONGODB_URI in .env
$env:COPILOT_GITHUB_TOKEN="github_pat_..."   # or sign in with the Copilot CLI instead
python scripts\check_env.py     # every line must be PASS (no FAIL)
uvicorn app.main:app --reload --port 8000
```
First start downloads the embedding model (about 90 MB) and indexes the knowledge base.

### Frontend (second terminal)
```powershell
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

### Tests (no Copilot, Mongo or internet needed)
```powershell
cd backend
python -m pytest -q tests
```

## Try it
"Plan a 3-day Goa trip for two people within ₹15,000. I like beaches, sightseeing and good food."
Then try a tight budget, e.g. ₹6,000, to watch the over-budget check, revision loop and automatic trimming.

## Flow
Planner (parse, strategy) -> Research (RAG + tools) -> loop { Planner draft -> Budget (Python maths) -> Itinerary builder ->
Reviewer } up to MAX_REVISIONS -> deterministic trim if still over budget -> you approve / revise / regenerate -> memory saved.

## Design notes
- The LLM only returns JSON text. Sessions deny every permission and expose no built-in tools. Our orchestrator calls plain Python tools.
- All arithmetic is Python (`app/tools/budget.py`). Prices are static approximate estimates and are labelled as such.
- Copilot calls per trip: 1 parse (only when you type a message) + 1 per draft attempt (max 1 + MAX_REVISIONS). Reviewer and Budget use no LLM.
- Every event in the Agent Activity page is a real backend event, stored in `agent_execution_logs`.
- Memory: `confirmed` (you stated/approved/edited) vs `assumed` (AI guess, only a soft hint).
- Single demo user via the `X-User-Id` header; there is no login and no password or token is stored.

## RAG availability and fallback

Semantic RAG (Sentence Transformers + ChromaDB) improves relevance but is optional at runtime. If the embedding stack cannot load (for example, a Windows Application Control policy blocks a native dependency), TravelMate falls back to keyword retrieval over the bundled destination knowledge base. Research also completes the activity and food catalog from that local knowledge base so itinerary generation does not depend on vector search. The deterministic planner validates that required catalog categories exist and reports a clear error instead of attempting modulo by zero.

All bundled destination prices are approximate estimates, not live quotes.
