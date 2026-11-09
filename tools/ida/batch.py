#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Run inside wine.py; dismiss only IDA's ordinary freeware About dialog."""
import ctypes
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def dismiss_about():
    tree = subprocess.check_output(["xwininfo", "-root", "-tree"], text=True)
    found = re.search(r'(0x[0-9a-f]+) "About".*?335x230\+(\d+)\+(\d+)', tree)
    if not found:
        return
    details = subprocess.check_output(["xwininfo", "-id", found[1]], text=True)
    if "IsViewable" not in details:
        return
    x = ctypes.CDLL("libX11.so.6")
    xt = ctypes.CDLL("libXtst.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xt.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    xt.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError("Cannot open virtual display")
    # Normal OK button; no modification to IDA or its licensing checks.
    xt.XTestFakeMotionEvent(display, -1, int(found[2]) + 294, int(found[3]) + 210, 0)
    xt.XTestFakeButtonEvent(display, 1, 1, 0)
    xt.XTestFakeButtonEvent(display, 1, 0, 0)
    x.XFlush(display)
    x.XCloseDisplay(display)


def main():
    wine = os.environ["IDA_WINE"]
    program = "/ida-install/extracted/app/idag.exe"
    env = dict(os.environ, IDALOG="Z:/ida-output/batch-ida.log")
    with Path("/ida-output/batch-wine.log").open("w") as log:
        child = subprocess.Popen([wine, program, "-A", "-a", "-pmn103", "-SZ:/ida-output/export.idc", "-oZ:/ida-output/main.idb", "Z:/ida-output/input.bin"], env=env, stdout=log, stderr=log)
        while child.poll() is None:
            dismiss_about()
            time.sleep(0.5)
        status = child.returncode
    # Flush the private Wine registry and stop only this prefix's services.
    subprocess.run([os.environ["IDA_WINESERVER"], "-k"], check=False)
    print(f"IDA process exit: {status}")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
