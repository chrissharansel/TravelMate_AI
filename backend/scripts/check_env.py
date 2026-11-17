"""Phase 1 environment inspector. Run from backend/:  python scripts/check_env.py
Prints PASS / FAIL / WARN per check and never prints secrets."""
import asyncio, os, platform, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

rows = []
def rec(name, status, detail=""):
    rows.append((name, status, detail))
    print(f"[{status:4}] {name}" + (f" - {detail}" if detail else ""))

def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, shell=(os.name == "nt"))
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else ""
    except Exception as e:
        return ""

rec("OS", "INFO", f"{platform.system()} {platform.release()}")
v = sys.version_info
rec("Python >= 3.11", "PASS" if v >= (3, 11) else "FAIL", f"{v.major}.{v.minor}.{v.micro}")
rec("Virtual env active", "PASS" if sys.prefix != sys.base_prefix else "WARN",
    "" if sys.prefix != sys.base_prefix else "run .venv\\Scripts\\activate first")
node = run(["node", "--version"])
rec("Node.js (for Phase 5 frontend)", "PASS" if node else "WARN", node or "not found; install Node 20+ before Phase 5")
rec("git", "PASS" if shutil.which("git") else "WARN", "")
cli = shutil.which("copilot")
rec("Copilot CLI on PATH (optional)", "PASS" if cli else "INFO", run(["copilot", "--version"]) if cli else "not needed if you use a token")
tok = [k for k in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN") if os.environ.get(k)]
rec("Token env var", "PASS" if tok else "INFO", ", ".join(tok) if tok else "none set; will rely on signed-in CLI user")
env_file = Path(".env")
rec("backend/.env exists", "PASS" if env_file.exists() else "FAIL", "" if env_file.exists() else "copy .env.example to .env")

async def deep():
    try:
        from app.config import get_settings
        s = get_settings()
        rec("MONGODB_URI set", "PASS" if s.mongodb_uri else "FAIL", "")
    except Exception as e:
        rec("Settings load", "FAIL", str(e)); return
    if s.mongodb_uri:
        try:
            from app.db import ping_db, close_db
            await ping_db(); await close_db()
            rec("MongoDB ping", "PASS", s.mongodb_database)
        except Exception as e:
            rec("MongoDB ping", "FAIL", f"{type(e).__name__}: {str(e)[:150]}")
    try:
        from app.knowledge import rag
        n = await asyncio.to_thread(rag.build_index)
        hits = await asyncio.to_thread(rag.search, "beaches", "Goa", "activity", 3)
        rec("RAG (ChromaDB + embeddings)", "PASS" if hits else "FAIL", f"{n} docs indexed; top hit: {hits[0][0]['name'] if hits else 'none'}")
    except Exception as e:
        rec("RAG (ChromaDB + embeddings)", "FAIL", f"{type(e).__name__}: {str(e)[:200]} (first run downloads a ~90 MB model)")
    try:
        from app import copilot_service as cs
        st = await cs.auth_status()
        rec("Copilot auth status", "PASS" if st.get("isAuthenticated", st.get("is_authenticated", True)) else "FAIL", str({k: v for k, v in st.items() if "token" not in k.lower()}))
        rec("Copilot models visible", "INFO", ", ".join((await cs.models())[:8]))
        reply = await cs.ask("Reply with exactly: TRAVELMATE_OK")
        rec("Copilot basic reply", "PASS" if "TRAVELMATE_OK" in reply else "WARN", reply[:80])
    except Exception as e:
        rec("Copilot", "FAIL", str(e)[:300])
    finally:
        try: await cs.stop_copilot()
        except Exception: pass

asyncio.run(deep())
print("\nPhase 1 passes only if there are no FAIL lines.")
sys.exit(1 if any(r[1] == "FAIL" for r in rows) else 0)
