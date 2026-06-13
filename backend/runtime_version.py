import os

# Semantic hub version. Used for update comparisons and Home Assistant sw_version.
SOFTWARE_VERSION = "1.0.0"

# Short git revision injected at image build time via the Docker build arg HUB_BUILD_REF
# (set by the Jenkins pipeline). Empty for local/dev builds.
BUILD_REF = os.getenv("HUB_BUILD_REF", "").strip()

# Human-facing version string, e.g. "1.0.0 (a1b2c3d)" when a build ref is present.
DISPLAY_VERSION = f"{SOFTWARE_VERSION} ({BUILD_REF})" if BUILD_REF else SOFTWARE_VERSION
