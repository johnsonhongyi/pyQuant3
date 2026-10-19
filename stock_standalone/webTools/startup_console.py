"""Hide the legacy version probe before importing the eager window_manager package."""
import os
import platform
import subprocess
import sys


def _quiet_syscmd_ver(system='', release='', version='',
                      supported_platforms=('win32', 'win16', 'dos')):
    """Preserve platform._syscmd_ver's parsing, defaults and fallback commands."""
    if sys.platform not in supported_platforms:
        return system, release, version
    for command in ('ver', 'command /c ver', 'cmd /c ver'):
        try:
            info = subprocess.check_output(command, stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, text=True, shell=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.CalledProcessError):
            continue
        break
    else:
        return system, release, version
    match = platform._ver_output.match(info.strip())
    if match is not None:
        system, release, version = match.groups()
        if release[-1] == '.':
            release = release[:-1]
        if version[-1] == '.':
            version = version[:-1]
        version = platform._norm_version(version)
    return system, release, version


def install_quiet_version_probe():
    """Install before keyboard/commonTips imports; never intercept general Popen."""
    if os.name != 'nt':
        return
    # These are the legacy CPython parser contracts in the pinned build runtime.
    if all(hasattr(platform, name) for name in ('_syscmd_ver', '_ver_output', '_norm_version')):
        platform._syscmd_ver = _quiet_syscmd_ver
