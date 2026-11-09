#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Run the optional IDA batch exporter with a virtual display and isolated mounts."""
import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=180)
    args = p.parse_args()
    install, output = args.installation.resolve(), args.out.resolve()
    if not (install/'extracted/app/idag.exe').is_file() or not (install/'prefix').is_dir():
        p.error('Expected extracted/app/idag.exe and an initialized 32-bit prefix')
    if not (output/'export.idc').is_file():
        p.error('Prepare the export first')
    local = (install/'runtime/usr/lib/wine/wine').is_file()
    runtime = '/ida-install/runtime'
    env = {'PATH': '/usr/bin:/bin', 'WINEPREFIX': '/ida-install/prefix', 'WINEARCH': 'win32',
           'WINEDEBUG': '-all', 'WINEDLLOVERRIDES': 'winemenubuilder.exe=d;mscoree,mshtml=d',
           'IDA_WINE': '/usr/bin/wine', 'IDA_WINESERVER': '/usr/bin/wineserver'}
    xvfb = '/usr/bin/xvfb-run'
    if local:
        env.update(PATH=runtime+'/usr/bin:/usr/bin:/bin',
                   WINELOADER=runtime+'/usr/lib/wine/wine', WINESERVER=runtime+'/usr/lib/wine/wineserver32',
                   WINEDLLPATH=runtime+'/usr/lib/i386-linux-gnu/wine',
                   LD_LIBRARY_PATH=':'.join(runtime+s for s in ('/usr/lib/i386-linux-gnu/wine','/usr/lib/i386-linux-gnu','/lib/i386-linux-gnu','/usr/lib/i386-linux-gnu/pulseaudio')),
                   IDA_WINE=runtime+'/usr/lib/wine/wine', IDA_WINESERVER=runtime+'/usr/lib/wine/wineserver32')
        xvfb=runtime+'/usr/bin/xvfb-run'
    cmd=['bwrap','--die-with-parent','--new-session','--unshare-all']
    for directory in ('/usr','/bin','/sbin','/lib','/lib64','/etc'):
        if Path(directory).exists():cmd += ['--ro-bind',directory,directory]
    cmd += ['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/home','--dir',str(Path.home()),
            '--ro-bind',str(HERE),'/ida-tools','--bind',str(install),'/ida-install',
            '--bind',str(output),'/ida-output','--chdir','/ida-output']
    if local:
        cmd += ['--ro-bind',str(HERE/'wineserver'),runtime+'/usr/lib/wine/wineserver']
    for key,value in env.items():cmd += ['--setenv',key,value]
    cmd += [xvfb,'-a','python3','/ida-tools/batch.py']
    try:subprocess.run(cmd,check=True,timeout=args.timeout)
    except subprocess.TimeoutExpired:sys.exit('IDA export exceeded its time limit')


if __name__ == '__main__':
    main()
