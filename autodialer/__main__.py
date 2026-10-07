"""``python -m autodialer`` -> run the API server.

``python -m autodialer dial <number>`` -> dial a single number right now
(handy for testing the phone setup without the API).

``python -m autodialer inspect`` -> show what the tool sees on the dialer screen.
"""

from __future__ import annotations

import argparse
import json
import logging

from .adb import AdbDevice
from .config import Settings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="autodialer")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the HTTP API (default)")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    d = sub.add_parser("dial", help="dial one number on the phone GUI now")
    d.add_argument("number")
    sub.add_parser("inspect", help="open the keypad and print the detected controls")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()

    if args.cmd in (None, "serve"):
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(settings), host=getattr(args, "host", "0.0.0.0"),
                    port=getattr(args, "port", 8000))
        return 0

    device = AdbDevice(settings.adb_serial, settings.adb_path)
    if args.cmd == "inspect":
        from .ui import find_dialer_screen, parse_dump
        device.open_dialer(settings.dialer_package)
        import time; time.sleep(1.5)
        scr = find_dialer_screen(parse_dump(device.dump_ui()), settings.id_overrides)
        print(json.dumps({
            "package": scr.package,
            "keys_found": sorted(scr.keys),
            "digits_field": scr.digits_field.resource_id if scr.digits_field else None,
            "call_button": scr.call_button.__dict__ if scr.call_button else None,
            "delete_button": scr.delete_button.__dict__ if scr.delete_button else None,
        }, indent=2))
        return 0

    from .dialer import GuiDialer
    from .notify import Notifier
    from .jobs import CallRequest, Job
    r = GuiDialer(device, dialer_package=settings.dialer_package, id_overrides=settings.id_overrides).dial(args.number)
    job = Job(id="cli", request=CallRequest(phone_number=args.number), status=r.outcome.value, result=r)
    Notifier(device, settings.notify_on_phone).job_finished(job)
    print(json.dumps(job.public(), indent=2))
    return 0 if r.called else 1


if __name__ == "__main__":
    raise SystemExit(main())
