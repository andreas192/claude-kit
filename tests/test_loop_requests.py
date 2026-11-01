import json

import pytest

from kit.errors import KitError
from kit.loop.requests import RequestRecord, add_requests, read_requests, request_lines


def test_records_are_kept_per_branch_and_appended(tmp_path):
    add_requests(tmp_path, "loop/a", [RequestRecord("investment", "T", url="https://x/1")])
    add_requests(tmp_path, "loop/a", [RequestRecord("investment", "U", error="refused")])
    add_requests(tmp_path, "loop/b", [RequestRecord("investment", "V", url="https://x/2")])
    assert [r.title for r in read_requests(tmp_path, "loop/a")] == ["T", "U"]
    stored = json.loads((tmp_path / "requests.json").read_text())
    assert stored["loop/b"] == [{"target": "investment", "title": "V", "url": "https://x/2"}]
    assert stored["loop/a"][1] == {"target": "investment", "title": "U", "error": "refused"}


def test_runtime_dir_is_created(tmp_path):
    runtime = tmp_path / "loop" / "repo"
    add_requests(runtime, "loop/a", [RequestRecord("investment", "T", url="u")])
    assert read_requests(runtime, "loop/a") == [RequestRecord("investment", "T", url="u")]


def test_no_file_is_no_records(tmp_path):
    assert read_requests(tmp_path, "loop/a") == []


def test_unknown_branch_is_no_records(tmp_path):
    add_requests(tmp_path, "loop/a", [RequestRecord("investment", "T", url="u")])
    assert read_requests(tmp_path, "loop/z") == []


@pytest.mark.parametrize(
    "text",
    ["{not json", "[]", '{"loop/a": "x"}', '{"loop/a": [{"target": "t"}]}', '{"loop/a": [{"target": "t", "title": "T"}]}'],
)
def test_malformed_file_is_a_one_line_kit_error(tmp_path, text):
    (tmp_path / "requests.json").write_text(text)
    with pytest.raises(KitError) as err:
        read_requests(tmp_path, "loop/a")
    assert "\n" not in str(err.value)
    assert "requests.json" in str(err.value)


@pytest.mark.parametrize("record", [RequestRecord("t", "T"), RequestRecord("t", "T", url="u", error="e")])
def test_record_needs_exactly_one_of_url_and_error(tmp_path, record):
    with pytest.raises(KitError, match="exactly one"):
        add_requests(tmp_path, "loop/a", [record])
    assert not (tmp_path / "requests.json").exists()


def test_request_lines():
    assert request_lines([RequestRecord("investment", "T", url="u"), RequestRecord("investment", "U", error="why")]) == [
        "- filed on investment: T: u",
        "- failed on investment: U: why",
    ]
