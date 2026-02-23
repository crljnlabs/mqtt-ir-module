import re
from pathlib import Path

Import("env")

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DEFAULT_VERSION = "0.0.1"


def normalize_version(raw: str) -> str:
    candidate = str(raw or "").strip()
    if candidate.startswith("v"):
        candidate = candidate[1:]
    if not SEMVER_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid firmware version '{raw}'. Expected x.y.z or vx.y.z.")
    return candidate


project_dir = Path(env.subst("$PROJECT_DIR"))
version_path = project_dir / "VERSION"

if not version_path.is_file():
    version_path.write_text(f"{DEFAULT_VERSION}\n", encoding="utf-8")

raw_version = version_path.read_text(encoding="utf-8").strip()
firmware_version = normalize_version(raw_version)

env.Append(
    CPPDEFINES=[
        ("AGENT_FIRMWARE_VERSION", f'\\"{firmware_version}\\"'),
    ]
)

print(f"Using firmware version: {firmware_version}")
