import os
import textwrap

import pytest

import prefect.settings
from prefect.settings import (
    DEFAULT_PROFILES,
    PREFECT_API_URL,
    PREFECT_LOGGING_EXTRA_LOGGERS,
    PREFECT_LOGGING_LEVEL,
    PREFECT_ORION_DATABASE_ECHO,
    PREFECT_TEST_MODE,
    Settings,
    get_current_settings,
    load_profile,
    load_profiles,
    write_profiles,
)
from prefect.utilities.testing import temporary_settings


def test_get_value_root_setting():
    with temporary_settings(PREFECT_API_URL="test"):  # Set a value so its not null
        value = prefect.settings.PREFECT_API_URL.value()
        value_of = get_current_settings().value_of(PREFECT_API_URL)
        value_from = PREFECT_API_URL.value_from(get_current_settings())
        assert value == value_of == value_from == "test"


def test_get_value_nested_setting():
    value = prefect.settings.PREFECT_LOGGING_LEVEL.value()
    value_of = get_current_settings().value_of(PREFECT_LOGGING_LEVEL)
    value_from = PREFECT_LOGGING_LEVEL.value_from(get_current_settings())
    assert value == value_of == value_from


def test_settings():
    assert PREFECT_TEST_MODE.value() is True


def test_settings_in_truthy_statements_use_value():
    if PREFECT_TEST_MODE:
        assert True, "Treated as truth"
    else:
        assert False, "Not treated as truth"

    with temporary_settings(PREFECT_TEST_MODE=False):
        if not PREFECT_TEST_MODE:
            assert True, "Treated as truth"
        else:
            assert False, "Not treated as truth"

    # Test with a non-boolean setting

    if PREFECT_LOGGING_LEVEL:
        assert True, "Treated as truth"
    else:
        assert False, "Not treated as truth"

    with temporary_settings(PREFECT_LOGGING_LEVEL=""):
        if not PREFECT_LOGGING_LEVEL:
            assert True, "Treated as truth"
        else:
            assert False, "Not treated as truth"


def test_temporary_settings():
    assert PREFECT_TEST_MODE.value() is True
    with temporary_settings(PREFECT_TEST_MODE=False) as new_settings:
        assert (
            PREFECT_TEST_MODE.value_from(new_settings) is False
        ), "Yields the new settings"
        assert PREFECT_TEST_MODE.value() is False, "Loads from env"
        assert PREFECT_TEST_MODE.value() is False, "Loads from context"

    assert PREFECT_TEST_MODE.value() is True, "Restores old setting"
    assert PREFECT_TEST_MODE.value() is True, "Restores old profile"


def test_temporary_settings_restores_on_error():
    assert PREFECT_TEST_MODE.value() is True

    with pytest.raises(ValueError):
        with temporary_settings(PREFECT_TEST_MODE=False):
            raise ValueError()

    assert os.environ["PREFECT_TEST_MODE"] == "1", "Restores os environ."
    assert PREFECT_TEST_MODE.value() is True, "Restores old setting"
    assert PREFECT_TEST_MODE.value() is True, "Restores old profile"


def test_refresh_settings(monkeypatch):
    assert PREFECT_TEST_MODE.value() is True

    monkeypatch.setenv("PREFECT_TEST_MODE", "0")
    new_settings = Settings()
    assert PREFECT_TEST_MODE.value_from(new_settings) is False


def test_nested_settings(monkeypatch):
    assert PREFECT_ORION_DATABASE_ECHO.value() is False

    monkeypatch.setenv("PREFECT_ORION_DATABASE_ECHO", "1")
    new_settings = Settings()
    assert PREFECT_ORION_DATABASE_ECHO.value_from(new_settings) is True


@pytest.mark.parametrize(
    "value,expected",
    [
        ("foo", ["foo"]),
        ("foo,bar", ["foo", "bar"]),
        ("foo, bar, foobar ", ["foo", "bar", "foobar"]),
    ],
)
def test_extra_loggers(value, expected):
    settings = Settings(PREFECT_LOGGING_EXTRA_LOGGERS=value)
    assert PREFECT_LOGGING_EXTRA_LOGGERS.value_from(settings) == expected


class TestProfiles:
    @pytest.fixture(autouse=True)
    def temporary_profiles_path(self, tmp_path):
        path = tmp_path / "profiles.toml"
        with temporary_settings(PREFECT_PROFILES_PATH=path):
            yield path

    def test_load_profiles_no_profiles_file(self):
        assert load_profiles() == DEFAULT_PROFILES

    def test_load_profiles_missing_default(self, temporary_profiles_path):
        temporary_profiles_path.write_text(
            textwrap.dedent(
                """
                [foo]
                PREFECT_API_KEY = "bar"
                """
            )
        )
        assert load_profiles() == {
            **DEFAULT_PROFILES,
            "foo": {"PREFECT_API_KEY": "bar"},
        }

    def test_load_profiles_with_default(self, temporary_profiles_path):
        temporary_profiles_path.write_text(
            textwrap.dedent(
                """
                [default]
                PREFECT_API_KEY = "foo"

                [foo]
                PREFECT_API_KEY = "bar"
                """
            )
        )
        assert load_profiles() == {
            "default": {"PREFECT_API_KEY": "foo"},
            "foo": {"PREFECT_API_KEY": "bar"},
        }

    def test_write_profiles_includes_default(self, temporary_profiles_path):
        write_profiles({})
        assert (
            temporary_profiles_path.read_text()
            == textwrap.dedent(
                """
                [default]
                """
            ).lstrip()
        )

    def test_write_profiles_allows_default_override(self, temporary_profiles_path):
        write_profiles({"default": {"PREFECT_API_KEY": "foo"}})
        assert (
            temporary_profiles_path.read_text()
            == textwrap.dedent(
                """
                [default]
                PREFECT_API_KEY = "foo"
                """
            ).lstrip()
        )

    def test_write_profiles_additional_profiles(self, temporary_profiles_path):
        write_profiles(
            {"foo": {"PREFECT_API_KEY": "bar"}, "foobar": {"PREFECT_API_KEY": 1}}
        )
        assert (
            temporary_profiles_path.read_text()
            == textwrap.dedent(
                """
                [default]

                [foo]
                PREFECT_API_KEY = "bar"

                [foobar]
                PREFECT_API_KEY = 1
                """
            ).lstrip()
        )

    def test_load_profile_default(self):
        assert load_profile("default") == {}

    def test_load_profile_missing(self):
        with pytest.raises(ValueError, match="Profile 'foo' not found."):
            load_profile("foo")

    def test_load_profile(self, temporary_profiles_path):
        temporary_profiles_path.write_text(
            textwrap.dedent(
                """
                [foo]
                PREFECT_API_KEY = "bar"
                PREFECT_DEBUG_MODE = 1
                """
            )
        )
        assert load_profile("foo") == {
            "PREFECT_API_KEY": "bar",
            "PREFECT_DEBUG_MODE": "1",
        }

    def test_load_profile_does_not_allow_nested_data(self, temporary_profiles_path):
        temporary_profiles_path.write_text(
            textwrap.dedent(
                """
                [foo]
                PREFECT_API_KEY = "bar"

                [foo.nested]
                """
            )
        )
        with pytest.raises(ValueError, match="Unknown setting.*'nested'"):
            load_profile("foo")

    def test_load_profile_with_invalid_key(self, temporary_profiles_path):
        temporary_profiles_path.write_text(
            textwrap.dedent(
                """
                [foo]
                test = "unknown-key"
                """
            )
        )
        with pytest.raises(ValueError, match="Unknown setting.*'test'"):
            load_profile("foo")
