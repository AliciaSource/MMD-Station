from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reload_addon():
    existing = sys.modules.get("mmd_station")
    if existing is not None:
        try:
            existing.unregister()
        except Exception:
            pass
    for name in list(sys.modules):
        if name == "mmd_station" or name.startswith("mmd_station."):
            del sys.modules[name]
    module = importlib.import_module("mmd_station")
    module.register()
    return module


def main():
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")
    from bl_ext.blender_org.mmd_tools.core import pmx
    from bl_ext.blender_org.mmd_tools.core.model import Model

    module = _reload_addon()
    try:
        from mmd_station.mmd_export_profile import last_export_profile
        from mmd_station.mmd_shadow import (
            clear_runtime_shadows,
            runtime_shadow_count,
        )

        model = Model.create("ShadowRegression", add_root_bone=True)
        root = model.rootObject()
        armature = model.armature()
        mesh = bpy.data.meshes.new("ShadowRegressionMesh")
        mesh.from_pydata(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            (),
            ((0, 1, 2),),
        )
        mesh_object = bpy.data.objects.new("ShadowRegressionMesh", mesh)
        bpy.context.collection.objects.link(mesh_object)
        material = bpy.data.materials.new("ShadowRegressionMaterial")
        mesh.materials.append(material)
        mesh_object.parent = armature
        modifier = mesh_object.modifiers.new(name="mmd_armature", type="ARMATURE")
        modifier.object = armature
        bpy.ops.object.select_all(action="DESELECT")
        root.select_set(True)
        bpy.context.view_layer.objects.active = root

        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.pmx"
            save_as = Path(directory) / "save-as.pmx"
            assert bpy.ops.mmd_tools.export_pmx(
                filepath=str(baseline),
                copy_textures_mode="NONE",
            ) == {"FINISHED"}
            assert baseline.is_file()
            assert runtime_shadow_count() == 1
            assert not last_export_profile().get("fast", False)

            probe_names = {
                "group_morphs": "ShadowAddedGroup",
                "bone_morphs": "ShadowAddedBone",
                "material_morphs": "ShadowAddedMaterial",
            }
            added = {}
            for collection_name, probe_name in probe_names.items():
                morph = getattr(root.mmd_root, collection_name).add()
                morph.name = probe_name
                morph.name_e = probe_name
                added[collection_name] = morph
            assert bpy.ops.mmd_tools.export_pmx(
                filepath=str(save_as),
                copy_textures_mode="SKIP_EXISTING",
            ) == {"FINISHED"}
            assert save_as.is_file()
            assert last_export_profile()["fast"] is True

            exported = pmx.load(str(save_as))
            assert set(probe_names.values()) <= {
                item.name
                for item in exported.morphs
            }

            renamed = "ShadowRenamedGroup"
            added["group_morphs"].name = renamed
            added["group_morphs"].name_e = renamed
            root.mmd_root.name = "ShadowRegressionRenamed"
            assert bpy.ops.mmd_tools.export_pmx(
                filepath=str(save_as),
                copy_textures_mode="SKIP_EXISTING",
            ) == {"FINISHED"}
            assert last_export_profile()["fast"] is True
            renamed_export = pmx.load(str(save_as))
            assert renamed_export.name == "ShadowRegressionRenamed"
            assert any(item.name == renamed for item in renamed_export.morphs)

            mesh.vertices[0].co.x += 0.25
            mesh.update()
            bpy.context.view_layer.update()
            fallback = Path(directory) / "fallback.pmx"
            assert bpy.ops.mmd_tools.export_pmx(
                filepath=str(fallback),
                copy_textures_mode="NONE",
            ) == {"FINISHED"}
            assert fallback.is_file()
            assert not last_export_profile().get("fast", False)
            assert runtime_shadow_count() == 1

        clear_runtime_shadows()
        assert runtime_shadow_count() == 0
        print("MMD_SHADOW_REGRESSION_OK")
    finally:
        module.unregister()


if __name__ == "__main__":
    main()
