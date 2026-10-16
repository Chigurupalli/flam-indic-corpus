
import gzip
import json
import os
import subprocess
import sys

import pytest
from tests import synth

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(raw, out, env=None, check=True):
    e = dict(os.environ, FLAM_SHARD_SIZE="100", **(env or {}))
    script = os.path.join(ROOT, "run.sh")

    if os.name == "nt":
        # Explicit Git Bash paths, avoiding the WSL launcher.
        bash_exe = r"C:\Program Files\Git\usr\bin\bash.exe"
        cygpath_exe = r"C:\Program Files\Git\usr\bin\cygpath.exe"

        if not os.path.isfile(bash_exe):
            raise FileNotFoundError(f"Git Bash not found: {bash_exe}")

        if not os.path.isfile(cygpath_exe):
            raise FileNotFoundError(f"cygpath not found: {cygpath_exe}")

        def bash_path(path):
            result = subprocess.run(
                [cygpath_exe, "-u", os.path.abspath(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()

        # Pass the active Python interpreter to run.sh.
        e["FLAM_PYTHON"] = bash_path(sys.executable)

        command = [
            bash_exe,
            bash_path(script),
            bash_path(raw),
            bash_path(out),
        ]
    else:
        e["FLAM_PYTHON"] = sys.executable
        command = [script, raw, out]

    result = subprocess.run(
        command,
        env=e,
        capture_output=True,
        text=True,
        check=False,
    )

    if check and result.returncode != 0:
        raise AssertionError(
            f"Pipeline exited with code {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def tree(out):
    res = {}

    for base, _, files in os.walk(out):
        if "_work" in base:
            continue

        for filename in files:
            path = os.path.join(base, filename)

            with open(path, "rb") as file:
                res[os.path.relpath(path, out)] = file.read()

    return res


def rows(path):
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file]


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    directory = str(tmp_path_factory.mktemp("raw"))
    synth.build(directory)
    return directory


def test_pipeline_outputs_and_rerun_determinism(raw, tmp_path):
    out1 = str(tmp_path / "o1")
    out2 = str(tmp_path / "o2")

    run(raw, out1)
    run(raw, out2)

    # Identical input should produce byte-identical output.
    assert tree(out1) == tree(out2)

    # Rerunning in the same output directory should remain deterministic.
    run(raw, out1)
    assert tree(out1) == tree(out2)

    ledger = rows(os.path.join(out1, "ledger.jsonl"))
    ids = [row["id"] for row in ledger]

    # One ledger row per input document.
    assert len(ids) == len(set(ids))

    reasons = {
        row["reason"].split(":")[0]
        for row in ledger
        if row["status"] == "dropped"
    }

    for want in (
        "bad_json",
        "no_text_field",
        "redirect",
        "truncated_or_corrupt_file",
        "exact_duplicate",
        "markup_html",
        "mojibake_utf8_as_latin1",
        "not_hindi",
        "eval_item",
    ):
        assert want in reasons, want

    clean = []
    clean_dir = os.path.join(out1, "clean")

    for filename in sorted(os.listdir(clean_dir)):
        if filename.endswith(".gz"):
            path = os.path.join(clean_dir, filename)

            with gzip.open(path, "rt", encoding="utf-8") as file:
                clean.extend(json.loads(line) for line in file)

    # Clean output must not contain duplicate IDs.
    assert len({doc["id"] for doc in clean}) == len(clean)

    # Only Hindi and Hinglish should remain in training data.
    assert {doc["lang"] for doc in clean} <= {"hi", "hi-Latn"}

    texts = "\n".join(doc["text"] for doc in clean)

    # Verify expected text and PII redaction.
    assert "जैसा बोओगे वैसा काटोगे" in texts
    assert "<PHONE>" in texts
    assert "<EMAIL>" in texts
    assert "<AADHAAR>" in texts
    assert "<PAN>" in texts

    # Ordinary numbers and years should remain.
    assert "1,50,000" in texts
    assert "1234567890" in texts
    assert "2023" in texts

    # Sensitive phone number should be redacted.
    assert "9876543210" not in texts

    kept_ids = {
        row["id"]
        for row in ledger
        if row["status"] == "kept"
    }

    assert kept_ids == {doc["id"] for doc in clean}

    with open(
        os.path.join(out1, "manifest.json"),
        encoding="utf-8",
    ) as file:
        manifest = json.load(file)

    assert manifest["counts"]["input_records"] == len(ledger)
    assert manifest["input_files"]

    eval_items = rows(os.path.join(out1, "eval.jsonl"))

    assert 0 < len(eval_items) <= 200

    held_ids = {
        row["reason"].split(":")[1]
        for row in ledger
        if row["stage"] == "holdout"
    }

    assert held_ids == {
        item["eval_id"]
        for item in eval_items
    }

    # Evaluation text must not appear verbatim in training text.
    for item in eval_items:
        assert item["text"] not in texts


def test_kill_and_resume_matches_clean_run(raw, tmp_path):
    reference = str(tmp_path / "ref")
    interrupted = str(tmp_path / "killed")

    run(raw, reference)

    # Simulate a crash after shard 2.
    result = run(
        raw,
        interrupted,
        env={"FLAM_CRASH_AFTER_SHARD": "2"},
        check=False,
    )

    assert result.returncode == 137

    assert not os.path.exists(
        os.path.join(interrupted, "manifest.json")
    )

    # Restart and verify that the pipeline resumes.
    result = run(raw, interrupted)

    assert "resumed from previous run" in result.stderr
    assert tree(reference) == tree(interrupted)
