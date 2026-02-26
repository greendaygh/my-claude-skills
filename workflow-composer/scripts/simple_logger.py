#!/usr/bin/env python3
"""simple_logger.py — Minimal execution logging for workflow composition."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class ExecutionLogger:
    """Simple phase-based execution logger."""

    def __init__(self, wf_dir: str | Path):
        self.wf_dir = Path(wf_dir)
        self.log_path = self.wf_dir / '00_metadata' / 'execution_log.json'
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.started = datetime.now(timezone.utc).isoformat()
        self.events: list[dict] = []
        self._phase_starts: dict[str, float] = {}

    def phase_start(self, phase: str, message: str = ""):
        """Log phase start."""
        self._phase_starts[phase] = time.time()
        self.events.append({
            'type': 'phase_start',
            'phase': phase,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        print(f"  Phase {phase}: {message}")

    def phase_end(self, phase: str, message: str = ""):
        """Log phase end with elapsed time."""
        elapsed = 0
        if phase in self._phase_starts:
            elapsed = round(time.time() - self._phase_starts[phase], 1)
            del self._phase_starts[phase]
        else:
            self.events.append({
                'type': 'warning',
                'phase': phase,
                'message': f"phase_end('{phase}') called without matching phase_start()",
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        self.events.append({
            'type': 'phase_end',
            'phase': phase,
            'message': message,
            'elapsed_seconds': elapsed,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        print(f"  Phase {phase} complete ({elapsed}s): {message}")

    def log(self, event_type: str, message: str, **kwargs):
        """Log a generic event."""
        entry = {
            'type': event_type,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
        self.events.append(entry)

    def error(self, message: str, **kwargs):
        """Log an error event."""
        self.log('error', message, **kwargs)
        print(f"  ERROR: {message}")

    def save(self):
        """Save log to disk."""
        total_elapsed = round(time.time() - self._start_time(), 1) if self.events else 0
        log_data = {
            'started': self.started,
            'total_elapsed_seconds': total_elapsed,
            'event_count': len(self.events),
            'events': self.events
        }
        with open(self.log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

    def _start_time(self) -> float:
        """Get epoch time of first event."""
        if self.events:
            try:
                ts = self.events[0]['timestamp']
                dt = datetime.fromisoformat(ts)
                return dt.timestamp()
            except Exception:
                pass
        return time.time()


def create_logger(wf_dir: str | Path) -> ExecutionLogger:
    """Create and return a new ExecutionLogger."""
    return ExecutionLogger(wf_dir)
