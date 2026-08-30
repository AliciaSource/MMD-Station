import ast
import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "mmd_station"
CJK = re.compile(r"[\u3400-\u9fff]")


def _catalog():
    path = PACKAGE / "i18n" / "catalog.py"
    spec = importlib.util.spec_from_file_location("mmd_station_i18n_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_trees():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "i18n" in path.parts or "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8-sig")
        yield path, source, ast.parse(source)


def test_every_chinese_source_message_has_an_english_catalog_entry():
    english = _catalog().ENGLISH
    missing = []
    for path, _source, tree in _source_trees():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and CJK.search(node.value)
                and node.value not in english
            ):
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
    assert not missing, "Missing English catalog entries:\n" + "\n".join(missing)


def test_user_facing_catalog_values_are_english():
    invalid = [
        (source, translated)
        for source, translated in _catalog().ENGLISH.items()
        if not source.startswith(";") and CJK.search(translated)
    ]
    assert not invalid


def test_runtime_ui_boundaries_are_localized():
    failures = []
    ui_methods = {
        "label",
        "operator",
        "prop",
        "menu",
        "popover",
        "template_list",
        "template_ID",
        "prop_search",
    }
    for path, source, tree in _source_trees():
        if "self.report(" in source:
            failures.append(f"{path.relative_to(ROOT)} still calls self.report directly")
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ui_methods
            ):
                continue
            for keyword in node.keywords:
                if keyword.arg != "text" or isinstance(keyword.value, ast.Constant):
                    continue
                if not (
                    isinstance(keyword.value, ast.Call)
                    and isinstance(keyword.value.func, ast.Name)
                    and keyword.value.func.id == "iface"
                ):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{keyword.value.lineno} has an unlocalized dynamic text argument"
                    )
    assert not failures, "\n".join(failures)


def test_dynamic_fragments_have_english_replacements():
    catalog = _catalog()
    invalid = [
        fragment
        for fragment in catalog.DYNAMIC_FRAGMENTS
        if fragment not in catalog.ENGLISH or CJK.search(catalog.ENGLISH[fragment])
    ]
    assert not invalid


def test_compatibility_identifiers_are_unchanged():
    source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    assert 'bl_idname = "SPX_PT_surface_proxy_creator"' in source
    assert "surface_proxy_creator" in source
    assert '"surface_proxy_armature"' in source
