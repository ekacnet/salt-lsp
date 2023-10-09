import tempfile
import time
from typing import Tuple

from salt_lsp.utils import FileUri


def doc_to_fileuri(doc: str) -> Tuple[str, FileUri]:
    dir = tempfile.mkdtemp(prefix="salt_lsp_test")
    with open(f"{dir}/{int(time.time())}", "w") as f:
        f.write(doc)
    uri = FileUri(f"file://{dir}")
    return dir, uri
