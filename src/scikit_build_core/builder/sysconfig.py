from __future__ import annotations

import os
import sysconfig
from pathlib import Path

from .._logging import logger

__all__ = ["get_python_include_dir", "get_python_library"]


def __dir__() -> list[str]:
    return __all__


def get_python_library() -> Path | None:
    libdirstr = sysconfig.get_config_var("LIBDIR")
    ldlibrarystr = sysconfig.get_config_var("LDLIBRARY")
    libdir = libdirstr and Path(libdirstr)
    ldlibrary = ldlibrarystr and Path(ldlibrarystr)
    multiarch = sysconfig.get_config_var("MULTIARCH")
    masd = sysconfig.get_config_var("multiarchsubdir")

    if libdir and ldlibrary and libdir.is_dir():
        if multiarch:
            if masd:
                if masd.startswith(os.sep):
                    masd = masd[len(os.sep) :]
                libdir_masd = libdir / masd
                if libdir_masd.is_dir():
                    libdir = libdir_masd
        libpath = Path(libdir) / ldlibrary
        if libpath.is_file():
            return libpath

    framework_prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
    if framework_prefix and Path(framework_prefix).is_dir() and ldlibrary:
        libpath = Path(framework_prefix) / ldlibrary
        if libpath.is_file():
            return libpath

    logger.error(
        "Can't find a Python library, got libdir={}, ldlibrary={}, multiarch={}, masd={}",
        libdir,
        ldlibrary,
        multiarch,
        masd,
    )
    return None


def get_python_include_dir() -> Path:
    return Path(sysconfig.get_path("include"))
