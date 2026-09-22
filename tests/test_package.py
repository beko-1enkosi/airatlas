from importlib import import_module


def test_airatlas_can_be_imported():
    package = import_module("airatlas")
    assert package.__name__ == "airatlas"
