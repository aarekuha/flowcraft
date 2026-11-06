import argparse
import logging
import signal
import time

from app.core.database import SessionLocal
from app.services.production_planner_service import ProductionPlannerService

LOGGER = logging.getLogger("flowcraft-planner")
STOP_REQUESTED = False


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def run_once() -> bool:
    session = SessionLocal()
    try:
        return ProductionPlannerService(session).run_once()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Flowcraft production planner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than zero")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if args.once:
        run_once()
        return

    LOGGER.info("planner started")
    while not STOP_REQUESTED:
        try:
            processed = run_once()
        except Exception:
            LOGGER.exception("planning calculation failed")
            processed = False
        if not processed:
            time.sleep(args.poll_seconds)
    LOGGER.info("planner stopped")


if __name__ == "__main__":
    main()
