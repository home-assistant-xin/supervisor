#!/usr/bin/env python3
# ruff: noqa: T201
"""Patch supervisor source for China acceleration at build time.

Replaces all sed-based GitHub Variables (VERSION_SOURCE, ADDONS_SOURCE,
GHCR_DOWNLOAD_SOURCE, OS_DOWNLOAD_SOURCE, REPLACE_REPOSITORY_NAME,
MODIFY_TIMEZONE) with a single unified script. Fixes two issues from the
original sed approach:
1. docker/interface.py: preserve pull_image_name from _get_credentials;
   use force=True for images.delete; place restore logic after latest tag.
2. os/manager.py: place the gh-proxy replace after the None check, not before.
"""
from __future__ import annotations

from pathlib import Path
import sys


def _replace_once(content: str, old: str, new: str, label: str) -> str:
    if old not in content:
        print(f"ERROR: patch '{label}' did not find expected text", file=sys.stderr)
        sys.exit(1)
    if content.count(old) > 1:
        print(
            f"ERROR: patch '{label}' matched multiple times", file=sys.stderr
        )
        sys.exit(1)
    return content.replace(old, new, 1)


def patch_interface(filepath: Path) -> None:
    """Patch docker/interface.py for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    content = _replace_once(
        content,
        '        credentials, pull_image_name = self._get_credentials(image)\n\n'
        '        listener = self.sys_bus.register_event(\n',
        '        credentials, pull_image_name = self._get_credentials(image)\n\n'
        '        # ===================== China accel: hassio-supervisor repo replace (region-independent) =====================\n'
        '        original_image_full = pull_image_name\n'
        '        if "-hassio-supervisor" in pull_image_name and pull_image_name.startswith(\n'
        '            "ghcr.io/home-assistant/"\n'
        '        ):\n'
        '            pull_image_name = pull_image_name.replace(\n'
        '                "ghcr.io/home-assistant/", "ghcr.io/home-assistant-xin/", 1\n'
        '            )\n'
        '            _LOGGER.debug(\n'
        '                "Detected hassio-supervisor image, replace repo name: %s",\n'
        '                pull_image_name,\n'
        '            )\n\n'
        '        # ===================== Region check, only controls ghcr domain mirror =====================\n'
        '        use_mirror_domain = False\n'
        '        mirror_domain = "ghcr.io"\n'
        '        try:\n'
        '            async with aiohttp.ClientSession() as session:\n'
        '                async with session.get(\n'
        '                    "https://services.home-assistant.io/whoami/v1/country",\n'
        '                    timeout=aiohttp.ClientTimeout(total=10),\n'
        '                ) as resp:\n'
        '                    country_code = (await resp.text()).strip()\n'
        '                    _LOGGER.debug("Detected country code: %s", country_code)\n'
        '                    if country_code == "CN":\n'
        '                        use_mirror_domain = True\n'
        '        except Exception as geo_err:\n'
        '            _LOGGER.warning(\n'
        '                "Failed fetch country info, skip ghcr domain mirror replace: %s",\n'
        '                geo_err,\n'
        '            )\n\n'
        '        if use_mirror_domain and pull_image_name.startswith("ghcr.io/"):\n'
        '            try:\n'
        '                async with aiohttp.ClientSession() as session:\n'
        '                    async with session.get(\n'
        '                        "https://os-artifacts.home-assistant.xin/ghcr",\n'
        '                        timeout=aiohttp.ClientTimeout(total=10),\n'
        '                    ) as mirror_resp:\n'
        '                        mirror_domain = (await mirror_resp.text()).strip()\n'
        '                        _LOGGER.debug(\n'
        '                            "Get random ghcr mirror domain: %s", mirror_domain\n'
        '                        )\n'
        '            except Exception as mirror_err:\n'
        '                _LOGGER.warning(\n'
        '                    "Fetch ghcr mirror domain failed, fallback use original ghcr.io: %s",\n'
        '                    mirror_err,\n'
        '                )\n'
        '                mirror_domain = "ghcr.io"\n'
        '            pull_image_name = pull_image_name.replace("ghcr.io", mirror_domain, 1)\n'
        '            _LOGGER.debug(\n'
        '                "Final pull image with mirror domain: %s", pull_image_name\n'
        '            )\n\n'
        '        listener = self.sys_bus.register_event(\n',
        "interface: insert accel logic after _get_credentials",
    )

    content = _replace_once(
        content,
        '        _LOGGER.info("Downloading docker image %s with tag %s.", image, version)\n',
        '        _LOGGER.info("Downloading docker image %s with tag %s.", pull_image_name, version)\n',
        "interface: log pull_image_name instead of image",
    )

    content = _replace_once(
        content,
        '            # Tag latest\n'
        '            if latest:\n'
        '                _LOGGER.info(\n'
        '                    "Tagging image %s with version %s as latest", image, version\n'
        '                )\n'
        '                await self.sys_docker.images.tag(\n'
        '                    docker_image["Id"], image, tag="latest"\n'
        '                )\n'
        '        except DockerRegistryRateLimitExceeded as err:\n',
        '            # Tag latest\n'
        '            if latest:\n'
        '                _LOGGER.info(\n'
        '                    "Tagging image %s with version %s as latest", image, version\n'
        '                )\n'
        '                await self.sys_docker.images.tag(\n'
        '                    docker_image["Id"], image, tag="latest"\n'
        '                )\n\n'
        '            # ===================== After pull: restore original tag + remove mirror temp tag =====================\n'
        '            if use_mirror_domain and mirror_domain != "ghcr.io":\n'
        '                await self.sys_docker.images.tag(\n'
        '                    docker_image["Id"], original_image_full, tag=str(version)\n'
        '                )\n'
        '                mirror_full_tag = f"{pull_image_name}:{str(version)}"\n'
        '                try:\n'
        '                    await self.sys_docker.images.delete(\n'
        '                        mirror_full_tag, force=True\n'
        '                    )\n'
        '                    _LOGGER.debug(\n'
        '                        "Removed mirror temp tag %s", mirror_full_tag\n'
        '                    )\n'
        '                except aiodocker.DockerError as del_err:\n'
        '                    _LOGGER.debug("Skip delete mirror tag: %s", del_err)\n'
        '        except DockerRegistryRateLimitExceeded as err:\n',
        "interface: insert restore logic after latest tag",
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


def patch_os_manager(filepath: Path) -> None:
    """Patch os/manager.py for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    content = _replace_once(
        content,
        '        raw_url = self.sys_updater.ota_url\n'
        '        if raw_url is None:\n'
        "            raise HassOSUpdateError(\"Don't have an URL for OTA updates!\", _LOGGER.error)\n",
        '        raw_url = self.sys_updater.ota_url\n'
        '        if raw_url is None:\n'
        "            raise HassOSUpdateError(\"Don't have an URL for OTA updates!\", _LOGGER.error)\n"
        '        raw_url = raw_url.replace(\n'
        '            "os-artifacts.home-assistant.io/",\n'
        '            "gh-proxy.org/https://github.com/home-assistant-xin/operating-system/releases/download/",\n'
        '        )\n',
        "os/manager: insert gh-proxy replace after None check",
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


def patch_const(filepath: Path) -> None:
    """Patch supervisor/const.py for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    content = _replace_once(
        content,
        'URL_HASSIO_APPS = "https://github.com/home-assistant/addons"\n',
        'URL_HASSIO_APPS = "https://gitee.com/home-assistant-xin/addons"\n',
        "const: replace URL_HASSIO_APPS",
    )
    content = _replace_once(
        content,
        'URL_HASSIO_APPARMOR = "https://version.home-assistant.io/apparmor_{channel}.txt"\n',
        'URL_HASSIO_APPARMOR = "https://version.home-assistant.xin/apparmor_{channel}.txt"\n',
        "const: replace URL_HASSIO_APPARMOR",
    )
    content = _replace_once(
        content,
        'URL_HASSIO_VERSION = "https://version.home-assistant.io/{channel}.json"\n',
        'URL_HASSIO_VERSION = "https://version.home-assistant.xin/{channel}.json"\n',
        "const: replace URL_HASSIO_VERSION",
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


def patch_store_const(filepath: Path) -> None:
    """Patch supervisor/store/const.py for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    content = _replace_once(
        content,
        '    COMMUNITY_APPS = "https://github.com/hassio-addons/repository"\n',
        '    COMMUNITY_APPS = "https://gitee.com/home-assistant-xin/repository"\n',
        "store/const: replace COMMUNITY_APPS",
    )
    content = _replace_once(
        content,
        '    ESPHOME = "https://github.com/esphome/home-assistant-addon"\n',
        '    ESPHOME = "https://gitee.com/home-assistant-xin/esphome"\n',
        "store/const: replace ESPHOME",
    )
    content = _replace_once(
        content,
        '    MUSIC_ASSISTANT = "https://github.com/music-assistant/home-assistant-addon"\n',
        '    MUSIC_ASSISTANT = "https://gitee.com/home-assistant-xin/music-assistant"\n',
        "store/const: replace MUSIC_ASSISTANT",
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


def patch_pyproject(filepath: Path) -> None:
    """Patch pyproject.toml for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    old = "https://github.com/home-assistant/"
    new = "https://github.com/home-assistant-xin/"
    count = content.count(old)
    if count == 0:
        print("ERROR: patch 'pyproject: replace repository URLs' did not find expected text", file=sys.stderr)
        sys.exit(1)
    content = content.replace(old, new)

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath} ({count} replacements)")


def patch_dockerfile(filepath: Path) -> None:
    """Patch Dockerfile for China acceleration."""
    content = filepath.read_text(encoding="utf-8")

    content = _replace_once(
        content,
        "    && pip3 install uv==0.10.9\n",
        "    && pip3 install uv==0.10.9 \\\n"
        "    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \\\n"
        '    && echo "Asia/Shanghai" > /etc/timezone\n',
        "Dockerfile: add Asia/Shanghai timezone",
    )

    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


def main() -> None:
    """Apply all China acceleration patches to supervisor source."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    patch_const(root / "supervisor" / "const.py")
    patch_store_const(root / "supervisor" / "store" / "const.py")
    patch_interface(root / "supervisor" / "docker" / "interface.py")
    patch_os_manager(root / "supervisor" / "os" / "manager.py")
    patch_pyproject(root / "pyproject.toml")
    patch_dockerfile(root / "Dockerfile")


if __name__ == "__main__":
    main()
