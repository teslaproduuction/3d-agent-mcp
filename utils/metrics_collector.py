"""
Metrics collector — SQLite-backed storage for generation pipeline metrics.
Records timing, resource usage, mesh quality, and GCI per generation run.
"""
import sqlite3
import asyncio
import threading
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

DB_PATH = Path("outputs/metrics/metrics.db")

# ─────────────────────────── Schema ────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS generations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT,
    timestamp               TEXT,
    model_name              TEXT,
    image_provider          TEXT,
    use_multiview           INTEGER DEFAULT 0,

    -- Timing (seconds)
    time_image_gen          REAL,
    time_3d_gen             REAL,
    time_postprocess        REAL,
    time_total              REAL,

    -- Peak resources during 3D generation
    peak_vram_gb            REAL,
    peak_cpu_pct            REAL,
    peak_ram_gb             REAL,
    avg_cpu_pct             REAL,

    -- Mesh geometry
    face_count              INTEGER,
    vertex_count            INTEGER,
    surface_area_cm2        REAL,
    total_volume_cm3        REAL,
    char_size_cm            REAL,
    edge_length_total_cm    REAL,
    cavity_volume_cm3       REAL DEFAULT 0,

    -- GCI components & total
    gci_surface             REAL,
    gci_topology            REAL,
    gci_cavity              REAL,
    gci_total               REAL,

    -- Mesh quality flags
    is_manifold             INTEGER DEFAULT 0,
    non_manifold_edges      INTEGER DEFAULT 0,
    component_count         INTEGER DEFAULT 1,
    file_size_mb            REAL,

    -- Generation params
    octree_resolution       INTEGER,
    inference_steps         INTEGER,

    -- Output file path
    output_file             TEXT
);
"""

# ─────────────────────────── Data class ────────────────────────────────────

@dataclass
class GenerationRecord:
    session_id:             str  = "default"
    timestamp:              str  = field(default_factory=lambda: datetime.now().isoformat())
    model_name:             str  = ""
    image_provider:         str  = ""
    use_multiview:          bool = False

    time_image_gen:         Optional[float] = None
    time_3d_gen:            Optional[float] = None
    time_postprocess:       Optional[float] = None
    time_total:             Optional[float] = None

    peak_vram_gb:           Optional[float] = None
    peak_cpu_pct:           Optional[float] = None
    peak_ram_gb:            Optional[float] = None
    avg_cpu_pct:            Optional[float] = None

    face_count:             Optional[int]   = None
    vertex_count:           Optional[int]   = None
    surface_area_cm2:       Optional[float] = None
    total_volume_cm3:       Optional[float] = None
    char_size_cm:           Optional[float] = None
    edge_length_total_cm:   Optional[float] = None
    cavity_volume_cm3:      float           = 0.0

    gci_surface:            Optional[float] = None
    gci_topology:           Optional[float] = None
    gci_cavity:             Optional[float] = None
    gci_total:              Optional[float] = None

    is_manifold:            bool            = False
    non_manifold_edges:     int             = 0
    component_count:        int             = 1
    file_size_mb:           Optional[float] = None

    octree_resolution:      Optional[int]   = None
    inference_steps:        Optional[int]   = None
    output_file:            str             = ""

# ─────────────────────────── DB helpers ────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


_conn_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _conn_get() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = _get_conn()
        return _conn


def save_record(rec: GenerationRecord) -> int:
    """Insert a GenerationRecord into the DB and return its id."""
    d = asdict(rec)
    d["use_multiview"] = int(d["use_multiview"])
    d["is_manifold"]   = int(d["is_manifold"])
    cols   = ", ".join(d.keys())
    placeholders = ", ".join("?" * len(d))
    sql = f"INSERT INTO generations ({cols}) VALUES ({placeholders})"
    conn = _conn_get()
    with _conn_lock:
        cur = conn.execute(sql, list(d.values()))
        conn.commit()
        return cur.lastrowid


def load_records(limit: int = 200) -> list[dict]:
    """Return the last `limit` records as dicts (newest first)."""
    conn = _conn_get()
    with _conn_lock:
        rows = conn.execute(
            "SELECT * FROM generations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def load_records_df():
    """Return all records as a pandas DataFrame."""
    import pandas as pd
    records = load_records(limit=10000)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

# ─────────────────────────── Resource sampler ──────────────────────────────

class ResourceSampler:
    """
    Background thread that samples CPU/RAM every second.
    After stopping, returns peak and average values.
    """

    def __init__(self):
        self._cpu_samples: list[float] = []
        self._ram_samples: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._stop.clear()
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        self._thread.join(timeout=3)
        cpu = self._cpu_samples or [0.0]
        ram = self._ram_samples or [0.0]
        return {
            "peak_cpu_pct": max(cpu),
            "avg_cpu_pct":  sum(cpu) / len(cpu),
            "peak_ram_gb":  max(ram),
        }

    def _run(self):
        while not self._stop.is_set():
            try:
                self._cpu_samples.append(psutil.cpu_percent(interval=None))
                self._ram_samples.append(psutil.virtual_memory().used / 1024**3)
            except Exception:
                pass
            self._stop.wait(timeout=1.0)


async def get_vram_gb() -> Optional[float]:
    """Query current VRAM usage from admin /gpu-stats (non-blocking)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get("http://admin:9001/gpu-stats")
            d = r.json()
            if d.get("vram_used") and d.get("vram_total"):
                return d["vram_used"] / 1024  # MiB → GiB
    except Exception:
        pass
    return None
