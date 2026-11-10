"""pytest.ini must actually be read: with the wrong section header pytest ignored the whole file for months."""


def test_pytest_ini_is_active(pytestconfig):
    registered = {line.split(":")[0].split("(")[0].strip() for line in pytestconfig.getini("markers")}
    assert {"unit", "voice_test", "fallback", "provider", "quick"} <= registered, \
        "pytest.ini markers are not registered: is the section header [pytest]?"
