import os
import tempfile
from pathlib import Path

os.environ.setdefault("CSU_DB_PATH", str(Path(tempfile.mkdtemp()) / "invest.db"))
