import io
import json

from tts.library_web import build_data, make_handler
from tts.soundbite import make_key


def fixture(tmp_path):
    library = tmp_path / "library"
    (library / "openai" / "demo").mkdir(parents=True)
    audio = b"tiny mp3 bytes"
    rel = "openai/demo/hello.mp3"
    (library / rel).write_bytes(audio)
    (library / "manifest.json").write_text(json.dumps({
        make_key("hello", "openai", "demo", "model"): {"text": "hello", "provider": "openai", "voice": "demo", "model": "model", "speed": 1.0, "file": rel, "bytes": len(audio)},
        make_key("what next?", "openai", "demo", "model"): {"text": "what next?", "provider": "openai", "voice": "demo", "model": "model", "speed": 1.0, "file": rel, "bytes": len(audio)},
    }))
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({"profiles": {"demo": {"provider": "openai", "voice": "demo", "character": "Test voice"}, "empty": {"provider": "openai", "voice": "missing"}}, "assignments": {"test-cockpit": {"profile": "demo", "say": "hello"}}}))
    casting = tmp_path / "casting.json"
    casting.write_text(json.dumps({"openai_model": "model", "elevenlabs_model": "el", "elevenlabs_settings": {"stability": .5, "similarity_boost": .5}, "clauses": ["what next?", "is done"]}))
    return library, profiles, casting, rel, audio


class OpenBytesIO(io.BytesIO):
    def close(self):
        pass


class FakeSocket:
    def __init__(self, request):
        self.input = io.BytesIO(request.encode())
        self.output = OpenBytesIO()

    def makefile(self, mode, *args):
        return self.input if "r" in mode else self.output


class FakeServer:
    server_address = ("127.0.0.1", 0)

    def __init__(self, handler):
        self.RequestHandlerClass = handler


def request(tmp_path, path, headers=""):
    sub = tmp_path / ("case-" + str(len(list(tmp_path.iterdir()))))
    sub.mkdir()
    library, profiles, casting, rel, audio = fixture(sub)
    data, allowed = build_data(library, profiles, casting)
    sock = FakeSocket(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n{headers}\r\n")
    handler = make_handler(data, allowed, library)
    handler(sock, ("127.0.0.1", 1234), FakeServer(handler))
    return sock.output.getvalue(), data, rel, audio


def test_api_shape_counts_and_missing_coverage(tmp_path):
    response, _, _, _ = request(tmp_path, "/api/library")
    headers, body = response.split(b"\r\n\r\n", 1)
    result = json.loads(body)
    assert b"200 OK" in headers
    assert set(("summary", "profiles", "clauses", "assignments", "sound_effects", "clips", "provider_breakdown", "voice_breakdown")) <= result.keys()
    assert result["summary"]["clips"] == 2
    assert result["summary"]["providers"] == 1
    assert result["profiles"][0]["coverage"] == 1
    assert result["profiles"][1]["coverage"] == 0
    assert result["profiles"][1]["clips"] == {}
    assert result["assignments"][0]["cockpit"] == "test-cockpit"


def test_audio_allowlist_range_and_rejections(tmp_path):
    page, _, _, _ = request(tmp_path, "/")
    assert b"200 OK" in page.split(b"\r\n", 1)[0]
    assert b"Library map" in page
    response, _, rel, audio = request(tmp_path, "/audio/openai/demo/hello.mp3")
    headers, body = response.split(b"\r\n\r\n", 1)
    assert b"200 OK" in headers and b"Content-Type: audio/mpeg" in headers
    assert body == audio
    response, _, _, _ = request(tmp_path, "/audio/openai/demo/hello.mp3", "Range: bytes=1-4\r\n")
    headers, body = response.split(b"\r\n\r\n", 1)
    assert b"206 Partial Content" in headers
    assert body == audio[1:5]
    for header, expected in (("Range: bytes=-4\r\n", audio[-4:]),
                             ("Range: bytes=2-\r\n", audio[2:])):
        response, _, _, _ = request(tmp_path, "/audio/openai/demo/hello.mp3", header)
        headers, body = response.split(b"\r\n\r\n", 1)
        assert b"206 Partial Content" in headers
        assert body == expected
    for header in ("Range: bytes=nope\r\n", "Range: bytes=999-\r\n"):
        response, _, _, _ = request(tmp_path, "/audio/openai/demo/hello.mp3", header)
        assert b"416" in response.split(b"\r\n", 1)[0]
    for path in ("/audio/../manifest.json", "/audio/%2Fetc%2Fpasswd", "/audio/unlisted.mp3"):
        response, _, _, _ = request(tmp_path, path)
        assert b"404" in response.split(b"\r\n", 1)[0], path


def test_elevenlabs_model_and_assignment_name_lookup(tmp_path):
    library, profiles, casting, _, audio = fixture(tmp_path)
    profile_data = json.loads(profiles.read_text())
    profile_data["profiles"]["eleven"] = {"provider": "elevenlabs", "voice": "voice-id"}
    profile_data["assignments"]["eleven-cockpit"] = {"profile": "eleven", "say": "Captain"}
    profile_data["assignments"]["default-cockpit"] = {"profile": "demo"}
    profiles.write_text(json.dumps(profile_data))
    casting_data = json.loads(casting.read_text())
    casting_data["clauses"] = ["what next?"]
    casting.write_text(json.dumps(casting_data))
    model = "el|s0.5|b0.5"
    (library / "elevenlabs").mkdir()
    (library / "elevenlabs" / "clip.mp3").write_bytes(audio)
    manifest = json.loads((library / "manifest.json").read_text())
    manifest[make_key("default-cockpit", "openai", "demo", "model")] = {
        "text": "default-cockpit", "provider": "openai", "voice": "demo",
        "model": "model", "file": "openai/demo/hello.mp3", "bytes": len(audio),
    }
    manifest[make_key("what next?", "elevenlabs", "voice-id", model)] = {"text": "what next?", "provider": "elevenlabs", "voice": "voice-id", "model": model, "file": "elevenlabs/clip.mp3", "bytes": len(audio)}
    manifest[make_key("Captain", "elevenlabs", "voice-id", model)] = {"text": "Captain", "provider": "elevenlabs", "voice": "voice-id", "model": model, "file": "elevenlabs/clip.mp3", "bytes": len(audio)}
    (library / "manifest.json").write_text(json.dumps(manifest))
    data, _ = build_data(library, profiles, casting)
    voice = next(p for p in data["profiles"] if p["id"] == "eleven")
    assert voice["coverage"] == 1
    assert voice["name_text"] == "Captain"
    assignment = next(a for a in data["assignments"] if a["cockpit"] == "eleven-cockpit")
    assert assignment["say"] == "Captain"
    assert assignment["name_clip"] == "elevenlabs/clip.mp3"
    default_assignment = next(a for a in data["assignments"] if a["cockpit"] == "default-cockpit")
    assert default_assignment["say"] == "default-cockpit"
    assert default_assignment["name_clip"] == "openai/demo/hello.mp3"


def test_audio_symlink_cannot_escape_library(tmp_path):
    library, profiles, casting, _, audio = fixture(tmp_path)
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(audio)
    (library / "escape.mp3").symlink_to(outside)
    manifest = json.loads((library / "manifest.json").read_text())
    manifest["escape"] = {"text": "escape", "provider": "sfx", "voice": "none", "file": "escape.mp3", "bytes": len(audio)}
    (library / "manifest.json").write_text(json.dumps(manifest))
    data, allowed = build_data(library, profiles, casting)
    sock = FakeSocket("GET /audio/escape.mp3 HTTP/1.1\r\nHost: localhost\r\n\r\n")
    handler = make_handler(data, allowed, library)
    handler(sock, ("127.0.0.1", 1234), FakeServer(handler))
    assert b"404" in sock.output.getvalue().split(b"\r\n", 1)[0]


def test_server_main_binds_loopback(tmp_path, monkeypatch):
    from tts import library_web

    library, profiles, casting, _, _ = fixture(tmp_path)
    captured = {}

    class Server:
        server_port = 8765

        def __init__(self, address, handler):
            captured["address"] = address

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(library_web, "ThreadingHTTPServer", Server)
    assert library_web.main(["--library", str(library), "--profiles", str(profiles), "--casting", str(casting)]) == 0
    assert captured["address"] == ("127.0.0.1", 8765)


def test_main_rejects_invalid_port_and_missing_manifest(tmp_path, capsys):
    from tts import library_web

    assert library_web.main(["--port", "0"]) == 1
    missing = tmp_path / "missing"
    missing.mkdir()
    assert library_web.main(["--library", str(missing)]) == 1
    assert "manifest.json" in capsys.readouterr().err


def entry(text, voice="demo", created="2026-01-01T00:00:00", model="model", provider="openai"):
    return make_key(text, provider, voice, model), {"text": text, "provider": provider, "voice": voice, "model": model, "speed": 1.0, "file": f"openai/demo/{abs(hash(text))}.mp3", "bytes": 1, "created": created}


def profile_fixture(tmp_path):
    library, profiles, casting, _, _ = fixture(tmp_path)
    manifest = json.loads((library / "manifest.json").read_text())
    for text, created in (("hello", "2026-01-01"), ("demo: b \"quoted\" <b>", "2026-01-03"), ("demo: a", "2026-01-02"), ("demo: tense", "2026-01-04"), ("loose line", "2026-01-05")):
        k, v = entry(text, created=created)
        manifest[k] = v
    (library / "manifest.json").write_text(json.dumps(manifest))
    p = json.loads(profiles.read_text())
    p["assignments"]["orphan"] = {"profile": "nope"}
    p["assignments"]["demo-two"] = {"profile": "demo", "say": "demo two"}
    profiles.write_text(json.dumps(p))
    c = json.loads(casting.read_text())
    c["expressive"] = {"lines": ["demo: tense"]}
    casting.write_text(json.dumps(c))
    (tmp_path / "lines").mkdir()
    (tmp_path / "lines" / "test-cockpit.txt").write_text("# header\ndemo: a\ndemo: never recorded\n")
    return build_data(library, profiles, casting)[0]


def test_profile_view_data(tmp_path):
    data = profile_fixture(tmp_path)
    demo, empty = data["profiles"]
    assert [m["text"] for m in demo["menu"]] == ["what next?", "is done"]
    assert demo["menu"][0]["file"] and demo["menu"][1]["file"] is None
    assert [n["text"] for n in demo["name_clips"]] == ["hello", "demo two"]
    assert demo["name_clips"][0]["file"] and demo["name_clips"][1]["file"] is None
    assert [c["cockpit"] for c in demo["cockpit_info"]] == ["test-cockpit", "demo-two"]
    assert empty["cockpits"] == [] and empty["recorded"] == []
    groups = {g["prefix"]: g["lines"] for g in demo["recorded"]}
    # list order first (stored or not), then the rest by recorded date
    assert [l["text"] for l in groups["demo"]] == ["demo: a", "demo: never recorded", "demo: b \"quoted\" <b>", "demo: tense"]
    assert groups["demo"][1]["file"] is None
    assert [l["expressive"] for l in groups["demo"]] == [False, False, False, True]
    assert [l["text"] for l in groups["other"]] == ["loose line"]
    assert all("what next?" != l["text"] and l["text"] != "hello" for g in groups.values() for l in g)


def test_unmatched_cockpit_and_special_chars_carried_as_data(tmp_path):
    data = profile_fixture(tmp_path)
    orphan = next(a for a in data["assignments"] if a["cockpit"] == "orphan")
    assert orphan["profile"] == "nope" and orphan["name_clip"] is None
    assert json.loads(json.dumps(data, ensure_ascii=False))  # serialises with quote and markup in a line
    from tts.library_web import PAGE
    assert "esc(item.text)" in PAGE and "#profile=" in PAGE
