import os
import zipfile

import pytest

from addonly import Refused, check_zip, listing, main, put


def mkzip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for n, data in members.items():
            z.writestr(n, data)
    return str(path)


def test_put_adds_one_file_and_nothing_else(tmp_path):
    d = tmp_path / "drop"
    d.mkdir()
    (d / "old.txt").write_text("keep me")
    src = tmp_path / "new.txt"
    src.write_text("hello")
    t = put(str(src), str(d))
    assert t == str(d / "new.txt") and (d / "new.txt").read_text() == "hello" and (d / "old.txt").read_text() == "keep me"
    assert set(listing(str(d))) == {"old.txt", "new.txt"}


def test_put_never_overwrites_any_kind_of_target(tmp_path):
    d = tmp_path / "drop"
    d.mkdir()
    src = tmp_path / "a.txt"
    src.write_text("new")
    (d / "a.txt").write_text("old")
    os.symlink(str(tmp_path / "nowhere"), str(d / "dangling"))
    (d / "sub").mkdir()
    for name in ("a.txt", "dangling", "sub"):
        with pytest.raises(Refused) as e:
            put(str(src), str(d), name)
        assert e.value.code == 3
    assert (d / "a.txt").read_text() == "old" and not (tmp_path / "nowhere").exists()


def test_put_refuses_linked_or_missing_folder(tmp_path):
    real = tmp_path / "real"
    (real / "in").mkdir(parents=True)
    os.symlink(str(real), str(tmp_path / "link"))
    src = tmp_path / "a.txt"
    src.write_text("x")
    for d in (tmp_path / "link", tmp_path / "link" / "in", tmp_path / "missing", src):
        with pytest.raises(Refused) as e:
            put(str(src), str(d))
        assert e.value.code == 3
    assert os.listdir(str(real / "in")) == []
    with pytest.raises(Refused) as e:
        put(str(src), str(real), "../escape.txt")
    assert e.value.code == 2


def test_check_zip_rules(tmp_path):
    ok = mkzip(tmp_path / "ok.zip", {"app-1/VERSION": "1.4.2\n", "app-1/main.py": "print(1)"})
    assert check_zip(ok, version_file="VERSION") == "1.4.2"
    assert check_zip(ok) == ""
    cases = {
        "big.zip": ({"a.bin": b"x" * 2048}, "over 1024 bytes"),
        "exe.zip": ({"tool.EXE": b"MZ"}, "denied extension"),
        "up.zip": ({"../evil.txt": b"x"}, "leaves the zip root"),
        "nover.zip": ({"a.txt": b"x"}, "no VERSION"),
        "badver.zip": ({"VERSION": "1.0; rm -rf /"}, "not a plain version"),
    }
    for name, (members, why) in cases.items():
        with pytest.raises(Refused, match=why) as e:
            check_zip(mkzip(tmp_path / name, members), max_member=1024, version_file="VERSION")
        assert e.value.code == 2
    crc = tmp_path / "crc.zip"
    mkzip(crc, {"a.txt": b"A" * 100})
    data = bytearray(crc.read_bytes())
    data[data.index(b"A" * 100)] = ord("B")  # same size, wrong CRC
    crc.write_bytes(bytes(data))
    with pytest.raises(Refused, match="zip test failed"):
        check_zip(str(crc))
    (tmp_path / "not.zip").write_text("plain text")
    with pytest.raises(Refused, match="does not open"):
        check_zip(str(tmp_path / "not.zip"))


def test_cli_exit_codes(tmp_path, capsys):
    d = tmp_path / "drop"
    d.mkdir()
    z = mkzip(tmp_path / "build.zip", {"VERSION": "2.0"})
    assert main(["check-zip", z, "--version-file", "VERSION"]) == 0
    assert "version 2.0" in capsys.readouterr().out
    assert main(["put", z, str(d), "--zip-check", "--name", "build-2.0.zip"]) == 0
    assert main(["put", z, str(d), "--name", "build-2.0.zip"]) == 3
    assert main(["put", mkzip(tmp_path / "x.zip", {"a.pkl": b"x"}), str(d), "--zip-check"]) == 2
    assert "refused" in capsys.readouterr().err
    assert sorted(os.listdir(str(d))) == ["build-2.0.zip"]
