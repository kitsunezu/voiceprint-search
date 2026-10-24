"""Keep webrtcvad compatible with setuptools releases without pkg_resources."""
from importlib.util import find_spec
from pathlib import Path

spec = find_spec("webrtcvad")
if spec is None or spec.origin is None:
    raise RuntimeError("webrtcvad is missing")
path = Path(spec.origin)
source = path.read_text()
if "import pkg_resources" in source:
    old_version = "pkg_resources.get_distribution('webrtcvad').version"
    if old_version not in source:
        raise RuntimeError("Unexpected webrtcvad version lookup")
    source = source.replace("import pkg_resources", "from importlib.metadata import version")
    source = source.replace(old_version, "version('webrtcvad')")
    path.write_text(source)
