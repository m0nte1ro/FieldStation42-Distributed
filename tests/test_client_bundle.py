import pathlib
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).parents[1]


def test_client_bundle_has_the_client_and_nothing_of_the_server(tmp_path):
    out = subprocess.run(["bash", "client/platform/make_bundle.sh", "v9.9.9", str(tmp_path)], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(tmp_path / "fs42-client-v9.9.9.tar.gz")
    with tarfile.open(out) as bundle:
        names = bundle.getnames()
    assert {"fs42-client/client/main.py", "fs42-client/shared/rundown.py", "fs42-client/client/platform/install.sh",
            "fs42-client/docs/standby.png", "fs42-client/client.example.json", "fs42-client/LICENSE"} <= set(names)
    assert not [n for n in names if n.startswith("fs42-client/server") or "__pycache__" in n or n.endswith("client.json")]
