from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Generator, TypeVar

from packaging.version import Version

from ._logging import logger
from ._shutil import Run
from .errors import CMakeConfigError, CMakeNotFoundError, FailedLiveProcessError
from .program_search import best_program, get_cmake_programs

__all__ = ["CMake", "CMakeConfig"]


def __dir__() -> list[str]:
    return __all__


DIR = Path(__file__).parent.resolve()

Self = TypeVar("Self", bound="CMake")


@dataclasses.dataclass(frozen=True)
class CMake:
    version: Version
    cmake_path: Path

    @classmethod
    def default_search(
        cls: type[Self], *, minimum_version: Version | None = None, module: bool = True
    ) -> Self:
        candidates = get_cmake_programs(module=module)
        cmake_program = best_program(candidates, minimum_version=minimum_version)

        if cmake_program is None:
            raise CMakeNotFoundError(
                f"Could not find CMake with version >= {minimum_version}"
            )
        if cmake_program.version is None:
            msg = "CMake version undetermined @ {program.path}"
            raise CMakeNotFoundError(msg)

        return cls(version=cmake_program.version, cmake_path=cmake_program.path)

    def __fspath__(self) -> str:
        return os.fspath(self.cmake_path)


@dataclasses.dataclass
class CMakeConfig:
    cmake: CMake
    source_dir: Path
    build_dir: Path
    module_dirs: list[Path] = dataclasses.field(default_factory=list)
    prefix_dirs: list[Path] = dataclasses.field(default_factory=list)
    build_type: str = "Release"
    init_cache_file: Path = dataclasses.field(init=False, default=Path())
    env: dict[str, str] = dataclasses.field(init=False, default_factory=os.environ.copy)

    def __post_init__(self) -> None:
        self.init_cache_file = self.build_dir / "CMakeInit.txt"

        if not self.source_dir.is_dir():
            raise CMakeConfigError(f"source directory {self.source_dir} does not exist")

        self.build_dir.mkdir(parents=True, exist_ok=True)
        if not self.build_dir.is_dir():
            raise CMakeConfigError(
                f"build directory {self.build} must be a (creatable) directory"
            )

    def init_cache(
        self, cache_settings: Mapping[str, str | os.PathLike[str] | bool]
    ) -> None:
        with self.init_cache_file.open("w", encoding="utf-8") as f:
            for key, value in cache_settings.items():
                if isinstance(value, bool):
                    value = "ON" if value else "OFF"
                    f.write(f'set({key} {value} CACHE BOOL "")\n')
                elif isinstance(value, os.PathLike):
                    f.write(f'set({key} [===[{value}]===] CACHE PATH "")\n')
                else:
                    f.write(f'set({key} [===[{value}]===] CACHE STRING "")\n')
        contents = self.init_cache_file.read_text(encoding="utf-8").strip()
        logger.debug(
            "{}:\n{}",
            self.init_cache_file,
            textwrap.indent(contents.strip(), "  "),
        )

    def _compute_cmake_args(
        self, settings: Mapping[str, str | os.PathLike[str] | bool]
    ) -> Generator[str, None, None]:
        yield f"-S{self.source_dir}"
        yield f"-B{self.build_dir}"

        if self.init_cache_file.is_file():
            yield f"-C{self.init_cache_file}"

        if not sys.platform.startswith("win32"):
            logger.debug("Selecting Ninja; other generators currently unsupported")
            yield "-GNinja"
            if self.build_type:
                yield f"-DCMAKE_BUILD_TYPE={self.build_type}"

        for key, value in settings.items():
            if isinstance(value, bool):
                value = "ON" if value else "OFF"
                yield f"-D{key}:BOOL={value}"
            elif isinstance(value, os.PathLike):
                yield f"-D{key}:PATH={value}"
            else:
                yield f"-D{key}={value}"

        if self.module_dirs:
            module_dirs_str = ";".join(map(str, self.module_dirs))
            yield f"-DCMAKE_MODULE_PATH={module_dirs_str}"

        if self.prefix_dirs:
            prefix_dirs_str = ";".join(map(str, self.prefix_dirs))
            yield f"-DCMAKE_PREFIX_PATH={prefix_dirs_str}"

    def configure(
        self,
        *,
        defines: Mapping[str, str | os.PathLike[str] | bool] | None = None,
        cmake_args: Sequence[str] = (),
    ) -> None:
        _cmake_args = self._compute_cmake_args(defines or {})

        try:
            Run(env=self.env).live(self.cmake, *_cmake_args, *cmake_args)
        except subprocess.CalledProcessError:
            msg = "CMake configuration failed"
            raise FailedLiveProcessError(msg) from None

    def _compute_build_args(
        self,
        *,
        verbose: int,
    ) -> Generator[str, None, None]:
        for _ in range(verbose):
            yield "-v"
        if sys.platform.startswith("win32"):
            yield "--config"
            yield self.build_type

    def build(self, build_args: Sequence[str] = (), *, verbose: int = 0) -> None:
        local_args = self._compute_build_args(verbose=verbose)

        try:
            Run(env=self.env).live(
                self.cmake, "--build", self.build_dir, *build_args, *local_args
            )
        except subprocess.CalledProcessError:
            msg = "CMake build failed"
            raise FailedLiveProcessError(msg) from None

    def install(self, prefix: Path) -> None:
        try:
            Run(env=self.env).live(
                self.cmake,
                "--install",
                self.build_dir,
                "--prefix",
                prefix,
            )
        except subprocess.CalledProcessError:
            msg = "CMake install failed"
            raise FailedLiveProcessError(msg) from None
