"""The daily token report as a long-running service (v3.2: the compose service `usage-report`).

Writes reports/usage/YYYY-MM-DD.md + latest.md (the v3.1.1 daily report) once at startup, then every day at
07:00 in TIMEZONE — what the Mac's launchd job did before the agents moved to the server.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from datetime import time as clock
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import usage_report

REPORT_HOUR = 7
log = logging.getLogger("usage-report")


def next_run(now: datetime, hour: int = REPORT_HOUR) -> datetime:
    """The next local `hour`:00 strictly after `now` (aware), in now's zone."""
    today = datetime.combine(now.date(), clock(hour), tzinfo=now.tzinfo)
    return today if today > now else datetime.combine(now.date() + timedelta(days=1), clock(hour), tzinfo=now.tzinfo)


def seconds_until(now: datetime, target: datetime) -> float:
    """Real seconds, not wall-clock: correct across a DST switch."""
    return max(1.0, target.timestamp() - now.timestamp())


def write_report() -> None:
    try:
        usage_report.main(["--write", "reports/usage"])
    except Exception:
        log.exception("daily report not written (next try at the next run)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    tz = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv"))
    write_report()
    while True:
        now = datetime.now(tz)
        target = next_run(now)
        log.info("next report at %s", target.isoformat(timespec="minutes"))
        time.sleep(seconds_until(now, target))
        write_report()


if __name__ == "__main__":
    main()
