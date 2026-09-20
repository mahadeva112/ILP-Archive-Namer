"""Loads the code registries from data/*.json. Single source of truth."""
import json
import sys
from pathlib import Path

# When frozen by PyInstaller the bundle is unpacked to sys._MEIPASS.
_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA_DIR = _ROOT / "data"


def _load(name):
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class Registry:
    def __init__(self):
        self.channels = _load("channels.json")["channels"]
        self.departments = _load("departments.json")["departments"]
        self.languages = _load("languages.json")["languages"]
        self.nas = _load("nas_routes.json")
        self.template = _load("template.json")
        self._ch = {c["code"]: c for c in self.channels}
        self._dept = {d["code"]: d for d in self.departments}
        self._lang = {l["code"]: l for l in self.languages}

    def channel(self, code):
        return self._ch.get((code or "").upper())

    def department(self, code):
        return self._dept.get((code or "").upper())

    def language(self, code):
        return self._lang.get((code or "").lower())

    def nas_route(self, category):
        return self.nas["routes"].get(category)

    def prefix_for(self, channel_code, platform=None):
        """The literal folder prefix that precedes the language code.

        Resolves the spec's channel-code/platform-token ambiguity: if the
        registered code already ends with the platform token, it is used as-is;
        otherwise the token is appended (IEC + YT -> IECYT, matching the spec's
        own example IECYThin_...).
        """
        ch = self.channel(channel_code)
        if ch:
            return ch["prefix_literal"]
        code = (channel_code or "").upper()
        plat = (platform or "").upper()
        if plat and not code.endswith(plat):
            return code + plat
        return code


REGISTRY = Registry()
