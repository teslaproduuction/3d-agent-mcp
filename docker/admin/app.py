"""
Minimal admin webhook service.
POST /restart?token=<RESTART_TOKEN>  — restarts 3d-agent-app container
GET  /status                         — returns container status
"""
import os
import subprocess
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

RESTART_TOKEN = os.environ.get("RESTART_TOKEN", "")
APP_CONTAINER = os.environ.get("APP_CONTAINER", "3d-agent-app")
AI_CONTAINERS = [
    "3d-agent-hunyuan3d",
    "3d-agent-flux",
    "3d-agent-ollama",
    "3d-agent-app",
]


def _auth(qs: dict) -> bool:
    if not RESTART_TOKEN:
        return False
    token = qs.get("token", [""])[0]
    return token == RESTART_TOKEN


def _docker(*args) -> tuple[int, str]:
    result = subprocess.run(
        ["docker"] + list(args),
        capture_output=True, text=True, timeout=30
    )
    return result.returncode, (result.stdout + result.stderr).strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_restart(self, qs: dict):
        if not _auth(qs):
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>401 Unauthorized</h2>")
            return
        rc, out = _docker("restart", APP_CONTAINER)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if rc == 0:
            html = f"<h2>Restarting {APP_CONTAINER}...</h2><p>Done. Wait ~30s and reload the app.</p>"
        else:
            html = f"<h2>Error</h2><pre>{out}</pre>"
        self.wfile.write(html.encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/restart":
            self._handle_restart(qs)

        elif parsed.path == "/restart-all":
            if not _auth(qs):
                self.send_response(401)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h2>401 Unauthorized</h2>")
                return
            results = []
            for c in AI_CONTAINERS:
                rc, out = _docker("restart", c)
                results.append(f"{'OK' if rc == 0 else 'ERR'}: {c}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            lines = "<br>".join(results)
            html = f"<h2>Restarting all AI containers...</h2><p>{lines}</p><p>Wait ~60s and reload the app.</p>"
            self.wfile.write(html.encode())

        elif parsed.path == "/status":
            if not _auth(qs):
                self._send(401, {"error": "unauthorized"})
                return
            rc, out = _docker("inspect", "--format",
                               "{{.State.Status}}", APP_CONTAINER)
            status = out if rc == 0 else "unknown"

            # Memory usage for all containers via docker stats
            stats = {}
            rc2, out2 = _docker(
                "stats", "--no-stream", "--format",
                "{{.Name}}|{{.MemUsage}}|{{.MemPerc}}"
            )
            if rc2 == 0:
                for line in out2.splitlines():
                    parts = line.split("|")
                    if len(parts) == 3:
                        name, mem, perc = parts
                        stats[name.strip()] = {
                            "mem": mem.strip(),
                            "mem_pct": perc.strip()
                        }

            self._send(200, {
                "container": APP_CONTAINER,
                "status": status,
                "memory": stats
            })

        elif parsed.path == "/gpu-stats":
            # GPU stats via nvidia-smi inside hunyuan3d container (has CUDA devel)
            gpu_container = "3d-agent-hunyuan3d"
            rc, out = _docker(
                "exec", gpu_container,
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw,memory.used,memory.total,fan.speed",
                "--format=csv,noheader,nounits"
            )
            if rc == 0 and out.strip():
                parts = [p.strip() for p in out.strip().split(",")]
                try:
                    self._send(200, {
                        "name":       parts[0] if len(parts) > 0 else "N/A",
                        "temp_gpu":   int(parts[1])   if len(parts) > 1 else None,
                        "util_gpu":   int(parts[2])   if len(parts) > 2 else None,
                        "power_w":    float(parts[3]) if len(parts) > 3 else None,
                        "vram_used":  int(parts[4])   if len(parts) > 4 else None,
                        "vram_total": int(parts[5])   if len(parts) > 5 else None,
                        "fan_pct":    int(parts[6])   if len(parts) > 6 and parts[6] != "[N/A]" else None,
                    })
                except (ValueError, IndexError) as e:
                    self._send(200, {"error": f"parse error: {e}", "raw": out})
            else:
                self._send(200, {"error": f"nvidia-smi failed: {out}"})

        elif parsed.path == "/health":
            self._send(200, {"ok": True})

        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/restart", "/restart-all"):
            self.do_GET()
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9001))
    if not RESTART_TOKEN:
        print("WARNING: RESTART_TOKEN is not set — all requests will be rejected")
    print(f"Admin webhook listening on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
