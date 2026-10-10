import importlib.resources

import throttlebounce

# The public API. Add every exported name here as the library grows; this list is the
# contract and the test below fails if the module and this list disagree.
PUBLIC_API: list[str] = [
    "Clock",
    "Debounced",
    "Throttled",
    "TimerFactory",
    "debounce",
    "throttle",
]


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(throttlebounce.__all__) == sorted(PUBLIC_API)


def test_every_exported_name_resolves() -> None:
    for name in throttlebounce.__all__:
        assert hasattr(throttlebounce, name)


def test_version_is_a_three_part_string() -> None:
    parts = throttlebounce.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("throttlebounce").joinpath("py.typed").is_file()
