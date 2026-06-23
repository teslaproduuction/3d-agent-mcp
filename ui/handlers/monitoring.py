"""
Monitoring handler — collects GPU/CPU/RAM/container stats.
GPU: ComfyUI /system_stats endpoint (same Docker network).
CPU/RAM: psutil.
Containers: Docker stats via admin service or direct docker SDK.
"""
import psutil
import httpx
import asyncio
import logging
from collections import deque
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://flux:8188"
OLLAMA_URL  = "http://ollama:11434"
ADMIN_URL   = "http://admin:9001"

# Rolling history: last 60 data points (~10 min at 10 s interval)
_HISTORY_MAXLEN = 60
_gpu_history: deque = deque(maxlen=_HISTORY_MAXLEN)
_cpu_history: deque = deque(maxlen=_HISTORY_MAXLEN)
_ram_history: deque = deque(maxlen=_HISTORY_MAXLEN)


def _fmt_gb(bytes_val: int) -> str:
    return f"{bytes_val / 1024**3:.1f} GB"


def _fmt_pct(val: float) -> str:
    return f"{val:.1f}%"


def _clean_gpu_name(raw: str) -> str:
    """'cuda:0 NVIDIA H800 PCIe : cudaMallocAsync' → 'NVIDIA H800 PCIe'"""
    if raw.startswith("cuda:"):
        parts = raw.split(" ", 1)
        raw = parts[1] if len(parts) > 1 else raw
    if " : " in raw:
        raw = raw.split(" : ")[0]
    return raw.strip()


def _build_chart_df(history: deque, col: str) -> pd.DataFrame:
    """Build DataFrame with columns ['time', col] for gr.LinePlot."""
    if not history:
        return pd.DataFrame({"time": pd.Series(dtype="datetime64[ns]"), col: pd.Series(dtype=float)})
    times, values = zip(*history)
    return pd.DataFrame({"time": list(times), col: list(values)})


async def _get_gpu_stats() -> dict:
    """Fetch GPU stats: nvidia-smi via admin /gpu-stats (temp, util, power) + ComfyUI VRAM."""
    result = {"name": "N/A", "total": 0, "free": 0, "used": 0, "pct": 0,
              "util": "N/A", "temp": "N/A", "power": "N/A", "fan": "N/A"}
    async with httpx.AsyncClient(timeout=3) as client:
        # 1. nvidia-smi via admin service
        try:
            resp = await client.get(f"{ADMIN_URL}/gpu-stats")
            d = resp.json()
            if "error" not in d:
                result["name"]  = d.get("name", "N/A")
                result["temp"]  = f"{d['temp_gpu']}°C"  if d.get("temp_gpu")  is not None else "N/A"
                result["util"]  = f"{d['util_gpu']}%"   if d.get("util_gpu")  is not None else "N/A"
                result["power"] = f"{d['power_w']:.0f}W" if d.get("power_w") is not None else "N/A"
                result["fan"]   = f"{d['fan_pct']}%"    if d.get("fan_pct")   is not None else "N/A"
                if d.get("vram_total"):
                    used  = d["vram_used"]  * 1024 * 1024   # MiB → bytes
                    total = d["vram_total"] * 1024 * 1024
                    result["used"]  = used
                    result["total"] = total
                    result["free"]  = total - used
                    result["pct"]   = used / total * 100
        except Exception as e:
            logger.debug(f"Admin gpu-stats error: {e}")

        # 2. Fallback VRAM from ComfyUI if admin failed
        if result["total"] == 0:
            try:
                resp = await client.get(f"{COMFYUI_URL}/system_stats")
                devices = resp.json().get("devices", [])
                if devices:
                    d = devices[0]
                    total = d.get("vram_total", 0)
                    free  = d.get("vram_free", 0)
                    used  = total - free
                    result.update({
                        "name":  _clean_gpu_name(d.get("name", result["name"])),
                        "total": total, "free": free,
                        "used":  used,
                        "pct":   (used / total * 100) if total else 0,
                    })
            except Exception as e:
                logger.debug(f"ComfyUI gpu stats error: {e}")

    return result


async def _get_services_stats() -> list:
    """Ping known service endpoints for basic health."""
    services = [
        ("nginx",       "http://app:7860/",                   ""),
        ("app",         "http://app:7860/",                   ""),
        ("flux",        f"{COMFYUI_URL}/system_stats",        ""),
        ("hunyuan3d",   "http://hunyuan3d:8081/openapi.json", ""),
        ("ollama",      f"{OLLAMA_URL}/api/tags",             ""),
        ("redis",       None,                                  ""),
        ("admin",       "http://admin:9001/health",            ""),
    ]
    rows = []
    async with httpx.AsyncClient(timeout=2) as client:
        for name, url, _ in services:
            if url is None:
                rows.append([name, "✅ running", "—", "—"])
                continue
            try:
                r = await client.get(url)
                status = "✅ healthy" if r.status_code < 400 else f"⚠️ {r.status_code}"
            except Exception:
                status = "❌ unavailable"
            rows.append([name, status, "—", "—"])
    return rows


class MonitoringMixin:
    async def handle_get_monitoring_stats(self, session_id: str):
        """Return all hardware stats for the monitoring tab outputs."""
        gpu, services = await asyncio.gather(
            _get_gpu_stats(),
            _get_services_stats(),
        )

        # CPU
        cpu_pct   = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=False)
        cpu_log   = psutil.cpu_count(logical=True)
        try:
            freq = psutil.cpu_freq()
            cpu_freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
        except Exception:
            cpu_freq_str = "N/A"
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = None
            for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                if key in temps and temps[key]:
                    cpu_temp = temps[key][0].current
                    break
            cpu_temp_str = f"{cpu_temp:.0f}°C" if cpu_temp is not None else "N/A"
        except Exception:
            cpu_temp_str = "N/A"

        # RAM
        mem = psutil.virtual_memory()

        # Record history point
        now = datetime.now()
        _gpu_history.append((now, round(gpu["pct"], 1)))
        _cpu_history.append((now, round(cpu_pct, 1)))
        _ram_history.append((now, round(mem.percent, 1)))

        gpu_chart = _build_chart_df(_gpu_history, "VRAM %")
        cpu_chart = _build_chart_df(_cpu_history, "CPU %")
        ram_chart = _build_chart_df(_ram_history, "RAM %")

        return (
            # GPU
            gpu["name"],
            gpu["util"],
            gpu["temp"],
            gpu.get("power", "N/A"),
            gpu.get("fan", "N/A"),
            _fmt_gb(gpu["used"]),
            _fmt_gb(gpu["free"]),
            _fmt_gb(gpu["total"]),
            round(gpu["pct"], 1),
            # CPU
            _fmt_pct(cpu_pct),
            cpu_temp_str,
            f"{cpu_count}p / {cpu_log}t",
            cpu_freq_str,
            round(cpu_pct, 1),
            # RAM
            _fmt_gb(mem.used),
            _fmt_gb(mem.available),
            _fmt_gb(mem.total),
            round(mem.percent, 1),
            # Services
            services,
            # Charts
            gpu_chart,
            cpu_chart,
            ram_chart,
        )

    def handle_toggle_auto_refresh(self, enabled: bool):
        """Toggle the timer active state."""
        import gradio as gr
        return gr.Timer(active=enabled)
