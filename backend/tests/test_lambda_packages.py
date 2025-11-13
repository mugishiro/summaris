import zipfile
from pathlib import Path

import pytest

REQUIRED_SHARED_FILES = {
    "summarizer": {"shared/cloudflare.py"},
    "postprocess": {"shared/cloudflare.py"},
}


@pytest.mark.parametrize("package", sorted(REQUIRED_SHARED_FILES.keys()))
def test_lambda_packages_include_shared_helpers(package: str) -> None:
    zip_path = Path("dist") / f"{package}.zip"
    assert zip_path.exists(), f"Missing Lambda package: {zip_path}. Run the packaging step before tests."

    with zipfile.ZipFile(zip_path) as archive:
        contents = set(archive.namelist())

    missing = REQUIRED_SHARED_FILES[package] - contents
    assert not missing, f"{zip_path} is missing required files: {sorted(missing)}"
