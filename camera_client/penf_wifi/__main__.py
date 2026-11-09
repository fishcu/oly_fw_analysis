# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Linux development client. No command or a write without --execute is offline."""
import argparse
import json
from pathlib import Path
import sys

from .client import Camera
from .protocol import (AXES, TONES, ClientError, Setting, describe_plan,
                       load_json, recipe_plan)
from .recipes import snapshot_recipe
from .storage import CameraState, Run, save_json
from .transport import DEFAULT_AGENT, DEFAULT_REQUEST_GAP, HTTPTransport, base_url

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "runs"


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--camera", default="http://192.168.0.10", help="Camera HTTP origin")
    p.add_argument("--timeout", type=float, default=40, help="Socket timeout in seconds (default: 40)")
    p.add_argument("--ready-timeout", type=float, default=5,
                   help="Connection and read-only identification I/O timeout in seconds (default: 5)")
    p.add_argument("--request-gap", type=float, default=DEFAULT_REQUEST_GAP,
                   help=f"Pause after each HTTP connection, in seconds (default: {DEFAULT_REQUEST_GAP})")
    p.add_argument("--user-agent", default=DEFAULT_AGENT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Logs and persistent client state directory")
    commands = p.add_subparsers(dest="command")
    commands.add_parser("discover", help="Read camera identity, connection mode and supported commands")
    s = commands.add_parser("session", help="Explicitly enter/exit remote shooting; changes camera mode")
    s.add_argument("mode", choices=("rec", "play"))
    s = commands.add_parser("inspect", help="Save numeric settings of one COLOR profile")
    s.add_argument("--profile", required=True, type=int, choices=(1, 2, 3))
    s.add_argument("--recipe-out", type=Path, help="Also export a portable recipe to a NEW file")
    for command, help_text in (("read", "Read one setting"), ("set", "Plan one edit; --execute sends it")):
        s = commands.add_parser(command, help=help_text)
        s.add_argument("setting", choices=(*AXES, "contrast", *TONES))
        if command == "set":
            s.add_argument("value", type=int)
            s.add_argument("--execute", action="store_true")
        s.add_argument("--sector", type=int, help="Zero-based color index 0..11; H/S/L only")
        s.add_argument("--profile", required=True, type=int, choices=(1, 2, 3))
    for command, help_text in (
            ("apply", "Plan a JSON recipe; --execute sends it"),
            ("preview", "Read camera settings and show recipe differences; no writes"),
            ("verify", "Read camera settings; exit 0 if recipe matches, 3 if it does not")):
        s = commands.add_parser(command, help=help_text)
        s.add_argument("recipe", type=Path)
        s.add_argument("--profile", required=True, type=int, choices=(1, 2, 3))
        if command == "apply":
            s.add_argument("--execute", action="store_true")
    s = commands.add_parser("export", help="Offline: turn a saved snapshot into a portable recipe")
    s.add_argument("snapshot", type=Path)
    s.add_argument("--output", required=True, type=Path, help="New recipe file; never overwrites")
    s.add_argument("--name", help="Optional recipe name")
    s = commands.add_parser("compare", help="Offline comparison of two saved profile snapshots")
    s.add_argument("before", type=Path)
    s.add_argument("after", type=Path)
    s = commands.add_parser("acknowledge-reconnect", help="Local only: clear stop AFTER manually restarting camera Wi-Fi")
    s.add_argument("--after-manual-reconnect", required=True, action="store_true")
    return p


def compare(before_path, after_path):
    try:
        before, after = (json.loads(p.read_text()) for p in (before_path, after_path))
        for obj in (before, after):
            if (obj["format"] != "penf-wifi-snapshot-v1" or not isinstance(obj["values"], dict) or
                    not isinstance(obj["context"], dict)):
                raise ValueError("Not a client profile snapshot")
        if before["profile"] != after["profile"] or before["context"] != after["context"]:
            raise ValueError("Snapshot profiles/contexts differ; compare the same destination")
        a, b = before["values"], after["values"]
        return {"network_access": False, "profile": before["profile"],
                "changed": {k: {"before": a[k], "after": b[k]} for k in a.keys() & b.keys() if a[k] != b[k]},
                "not_comparable": sorted(a.keys() ^ b.keys()),
                "HL": {"before": before["HL"], "after": after["HL"]},
                "note": "Only reported values are compared; missing H/L is not assumed neutral."}
    except (KeyError, TypeError, ValueError) as e:
        raise ClientError(f"Cannot compare snapshots: {e}") from e


def emit(result):
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.command is None:
        p.print_help()
        return 0
    run = state = None
    try:
        plan, recommendations, setting = None, {}, None
        if args.command in ("read", "set"):
            setting = Setting(args.profile, args.setting, args.sector)
        if args.command == "set":
            plan = [(setting, setting.validate(args.value))]
        elif args.command in ("apply", "preview", "verify"):
            plan, recommendations = recipe_plan(args.recipe.read_text(), args.profile)
        if args.command in ("set", "apply") and not args.execute:
            emit(describe_plan(plan, recommendations))
            return 0
        if args.command == "export":
            snapshot = load_json(args.snapshot.read_text(), "snapshot JSON")
            recipe = snapshot_recipe(snapshot, args.name)
            save_json(args.output, recipe, overwrite=False)
            emit({"network_access": False, "recipe_file": str(args.output.resolve()),
                  "source_profile": snapshot["profile"], "settings": list(recipe["settings"]),
                  "HL": snapshot["HL"], "note": "Destination is chosen at upload; unknown H/L is omitted."})
            return 0
        if args.command == "compare":
            emit(compare(args.before, args.after))
            return 0
        if args.command == "inspect" and args.recipe_out is not None:
            if args.recipe_out.exists() or args.recipe_out.is_symlink():
                raise ClientError(f"Recipe output already exists: {args.recipe_out}; choose a new filename")
            if not args.recipe_out.parent.is_dir():
                raise ClientError(f"Recipe output directory does not exist: {args.recipe_out.parent}")

        camera_address = base_url(args.camera)
        run = Run(args.out, args.command)
        print(f"Run records: {run.path}", file=sys.stderr)
        run.save("invocation.json", {"command": args.command, "camera": camera_address,
                                    "user_agent": args.user_agent, "timeout": args.timeout,
                                    "ready_timeout": args.ready_timeout,
                                    "request_gap": args.request_gap})
        with CameraState(args.out, camera_address, run) as state:
            if args.command == "acknowledge-reconnect":
                result = state.acknowledge_reconnect()
            else:
                transport = HTTPTransport(camera_address, args.timeout, args.user_agent,
                                          run.record, request_gap=args.request_gap, ready_timeout=args.ready_timeout)
                camera = Camera(transport, progress=lambda message: print(message, file=sys.stderr, flush=True))
                if args.command == "discover":
                    result = camera.discover()
                elif args.command == "session":
                    result = camera.session(args.mode, state)
                elif args.command == "inspect":
                    result = camera.snapshot(args.profile)
                    run.save("snapshot.json", result)
                    if args.recipe_out is not None:
                        recipe = snapshot_recipe(result)
                        save_json(args.recipe_out, recipe, overwrite=False)
                        print(f"Recipe saved: {args.recipe_out.resolve()} (H/L: {result['HL']})",
                              file=sys.stderr)
                elif args.command in ("preview", "verify"):
                    run.save("plan.json", describe_plan(plan, recommendations))
                    result = camera.check(plan, run, recommendations)
                    result["client_stop_active"] = state.marker.exists()
                    if result["client_stop_active"]:
                        result["can_apply"] = False
                        result["upload_blockers"].append("An earlier operation is uncertain; see reconnect procedure")
                elif args.command == "read":
                    info, capability = camera.identify(), camera.capability()
                    result = {"camera": info, "capability": capability, "profile": args.profile,
                              "setting": setting.label, "value": camera.read(setting, capability["hsl1"])}
                else:
                    run.save("plan.json", describe_plan(plan, recommendations))
                    result = camera.apply(plan, state, recommendations)
            run.save("result.json", result)
        emit(result)
        return 3 if args.command == "verify" and not result["matches"] else 0
    except (ClientError, OSError, ValueError, KeyboardInterrupt) as e:
        error = {"error": str(e) or "Interrupted", "command": args.command,
                 "uncertain_operation": bool(state and state.marker.exists())}
        if run is not None:
            try:
                run.save("error.json", error)
            except OSError:
                pass
        print(f"Error: {error['error']}", file=sys.stderr)
        if error["uncertain_operation"]:
            print("Stopped with an uncertain outcome. No retry or rollback was sent. "
                  "See README: recovery after an interrupted operation.", file=sys.stderr)
        return 130 if isinstance(e, KeyboardInterrupt) else 2
    finally:
        if run is not None:
            run.close()


if __name__ == "__main__":
    sys.exit(main())
