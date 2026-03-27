import re
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from .routes.register import router as registry_router
from .routes.metrics import router as metrics_router
from .routes.checkpoints import router as checkpoints_router
from .routes.dashboard import router as dashboard_router

import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="LightML", lifespan=lifespan)

app.include_router(registry_router)
app.include_router(metrics_router)
app.include_router(checkpoints_router)
app.include_router(dashboard_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Launcher (used by CLI `gui` command)
# ─────────────────────────────────────────────

def _get_cloudflared() -> Path:
    """Return path to cloudflared binary from PATH, or raise if not found."""
    import shutil
    binary = shutil.which("cloudflared")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "cloudflared not found in PATH.\n"
        "  Install it from: https://developers.cloudflare.com/cloudflared/install/\n"
        "  Then re-run with --share."
    )


def _start_tunnel(port: int) -> None:
    """Launch cloudflared tunnel and print the public URL when ready."""
    try:
        binary = _get_cloudflared()
    except Exception as e:
        print(f"  Share: failed to get cloudflared — {e}")
        return

    proc = subprocess.Popen(
        [str(binary), "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in proc.stdout:
        m = re.search(r"https://[\w-]+\.trycloudflare\.com", line)
        if m:
            print(f"  Share: {m.group(0)}\n", flush=True)
            return


def launch(db_path: str, host: str = "0.0.0.0", port: int = 5050, share: bool = False):
    """Start the unified server with a dashboard backed by *db_path*."""
    db = Path(db_path).expanduser().resolve()
    if not db.exists():
        raise FileNotFoundError(f"Database not found: {db}")

    from lightml.database import migrate_database
    migrate_database(str(db))

    print(f"\n  LightML Dashboard")
    print(f"  DB:   {db}")
    print(f"  URL:  http://{host}:{port}")

    if share:
        threading.Thread(target=_start_tunnel, args=(port,), daemon=True).start()
    else:
        print()

    app.state.db_path = str(db)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=5000, reload=True)