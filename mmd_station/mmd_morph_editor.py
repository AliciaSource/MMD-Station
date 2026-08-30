import importlib
import json
import math
import re
import unicodedata
import urllib.error
import urllib.request
import uuid
from array import array
from contextlib import contextmanager

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, PropertyGroup, UIList
from mathutils import Vector

from .mmd_material_order import ordered_materials
from .mmd_morph_clipboard import (
    apply_pmx_editor_morphs,
    parse_pmx_editor_morph_csv,
    serialize_pmx_editor_morphs,
)


MORPH_TYPES = (
    ("material_morphs", "材质", "编辑 Material Morph"),
    ("uv_morphs", "UV", "编辑 UV、UV1～UV4 Morph"),
    ("bone_morphs", "骨骼", "编辑 Bone Morph"),
    ("vertex_morphs", "顶点", "编辑 Vertex Morph"),
    ("group_morphs", "群组", "编辑 Group Morph"),
)
ADDON_PACKAGE = __package__.split(".")[0]
MORPH_TYPE_KEYS = tuple(item[0] for item in MORPH_TYPES)
MORPH_UID_PROPERTY = "spx_morph_uid"
MATERIAL_UID_PROPERTY = "spx_morph_material_uid"
EDGE_PARENT_UID_PROPERTY = "spx_morph_edge_parent_uid"
OUTPUT_BRIDGE_PROPERTY = "spx_morph_output_bridge"
OUTPUT_GROUP_NAME = "SPX_MaterialMorphOutput"
UPSTREAM_ALPHA_PROPERTY = "spx_morph_original_alpha"
RUNTIME_BOUND_PROPERTY = "spx_morph_lightweight_bound"
RUNTIME_ERROR_PROPERTY = "spx_morph_runtime_error"
MATERIAL_BINDINGS_CLEAN_PROPERTY = "spx_morph_material_bindings_clean"
VERTEX_BINDINGS_CLEAN_PROPERTY = "spx_morph_vertex_bindings_clean"
DETAIL_SELECTED_PROPERTY = "spx_morph_detail_selected"
VERTEX_DETAIL_SELECTED_PROPERTY = "spx_morph_vertex_target_selected"
UV_DETAIL_SELECTED_PROPERTY = "spx_morph_uv_target_selected"
GROUP_FACTOR_PROXY_PROPERTY = "spx_morph_factor_live"

_MUTATING = False
_EVALUATING = False
_PENDING_STATE_REFRESHES = set()
_ORIGINAL_IMPORT_VMD_EXECUTE = None
_IMPORT_VMD_CLASS = None
_ORIGINAL_EXPORT_VMD_EXECUTE = None
_EXPORT_VMD_CLASS = None
_DETAIL_SELECTION_REGISTRATIONS = ()


class SPX_MorphAIAddonPreferences(AddonPreferences):
    bl_idname = ADDON_PACKAGE

    morph_ai_api_url: StringProperty(
        name="API 基础地址",
        description="只填写服务端基础地址，插件会自动追加 v1/chat/completions",
        default="",
    )
    morph_ai_api_key: StringProperty(
        name="API Key",
        subtype="PASSWORD",
    )
    morph_ai_model: StringProperty(
        name="调用模型",
        description="填写服务端实际支持的模型名称",
    )

    def draw(self, _context):
        _draw_morph_ai_settings(self.layout, self)


def _draw_morph_ai_settings(layout, settings):
    is_preferences = hasattr(settings, "morph_ai_api_url")
    layout.prop(settings, "morph_ai_api_url" if is_preferences else "api_url")
    layout.label(text="只填写基础地址；插件自动追加 /v1/chat/completions", icon="INFO")
    layout.prop(settings, "morph_ai_api_key" if is_preferences else "api_key")
    layout.prop(settings, "morph_ai_model" if is_preferences else "model")


def _addon_preferences(context):
    addon = context.preferences.addons.get(ADDON_PACKAGE)
    return addon.preferences if addon is not None else None


def _morph_ai_base_url(url):
    base_url = url.strip().rstrip("/")
    if base_url.lower().endswith("/v1"):
        base_url = base_url[:-3].rstrip("/")
    return base_url


def _morph_ai_chat_completions_url(url):
    base_url = _morph_ai_base_url(url)
    return base_url + "/v1/chat/completions" if base_url else ""


def _mmd_api():
    model_module = importlib.import_module("bl_ext.blender_org.mmd_tools.core.model")
    return model_module.FnModel, model_module.Model


def _root_poll(_self, obj):
    return obj is not None and getattr(obj, "mmd_type", "") == "ROOT"


def _find_root(context, settings):
    root = settings.morph_editor_root
    if _root_poll(None, root):
        return root
    active = context.active_object
    if active is None:
        return None
    try:
        FnModel, _Model = _mmd_api()
    except ImportError:
        return None
    return FnModel.find_root_object(active)


def _morph_collection(root, morph_type):
    return getattr(root.mmd_root, morph_type)


def _ensure_morph_uid(morph, used):
    uid = str(morph.get(MORPH_UID_PROPERTY, ""))
    if not uid or uid in used:
        uid = uuid.uuid4().hex
        morph[MORPH_UID_PROPERTY] = uid
    used.add(uid)
    return uid


def _morph_by_uid(root, morph_type, uid):
    if morph_type not in MORPH_TYPE_KEYS:
        return None
    for morph in _morph_collection(root, morph_type):
        if str(morph.get(MORPH_UID_PROPERTY, "")) == uid:
            return morph
    return None


def _morph_lookup(root):
    return {
        (morph_type, str(morph.get(MORPH_UID_PROPERTY, ""))): morph
        for morph_type in MORPH_TYPE_KEYS
        for morph in _morph_collection(root, morph_type)
    }


def _ordered_morphs(root):
    return [
        (morph_type, morph)
        for morph_type in MORPH_TYPE_KEYS
        for morph in _morph_collection(root, morph_type)
    ]


def _morph_states_are_current(root):
    if root is None or not hasattr(root, "spx_morph_states"):
        return False
    ordered = _ordered_morphs(root)
    states = root.spx_morph_states
    if len(states) != len(ordered):
        return False
    used = set()
    for state, (morph_type, morph) in zip(states, ordered):
        uid = str(morph.get(MORPH_UID_PROPERTY, ""))
        if not uid or uid in used:
            return False
        if (
            state.name != uid
            or state.uid != uid
            or state.morph_type != morph_type
            or state.morph_name != morph.name
        ):
            return False
        used.add(uid)
    return True


def _morph_state_structure_is_current(root):
    if root is None or not hasattr(root, "spx_morph_states"):
        return False
    live = {}
    for morph_type in MORPH_TYPE_KEYS:
        for morph in _morph_collection(root, morph_type):
            uid = str(morph.get(MORPH_UID_PROPERTY, ""))
            if not uid or uid in live:
                return False
            live[uid] = (morph_type, morph)
    states = root.spx_morph_states
    if len(states) != len(live):
        return False
    seen = set()
    for state in states:
        current = live.get(state.uid)
        if (
            state.uid in seen
            or state.name != state.uid
            or current is None
            or current[0] != state.morph_type
        ):
            return False
        seen.add(state.uid)
    return len(seen) == len(live)


def _refresh_morph_state_metadata(root):
    uv_runtime_renamed = False
    for state in root.spx_morph_states:
        morph = _morph_by_uid(root, state.morph_type, state.uid)
        if morph is not None and state.morph_name != morph.name:
            previous_name = state.morph_name
            uv_runtime_renamed = uv_runtime_renamed or (
                state.morph_type == "uv_morphs"
                and _bound_placeholder(root) is not None
                and bool(root.get(RUNTIME_BOUND_PROPERTY, False))
            )
            for frame in root.mmd_root.display_item_frames:
                for item in frame.data:
                    if (
                        item.type == "MORPH"
                        and item.morph_type == state.morph_type
                        and item.name == previous_name
                    ):
                        item.name = morph.name
            state.morph_name = morph.name
    ensure_morph_states(root)
    if uv_runtime_renamed:
        _ensure_lightweight_bind(root, force_rebind=True)


def _tag_view3d_redraw():
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _schedule_morph_state_refresh(root):
    if root is None:
        return
    try:
        key = root.as_pointer()
    except ReferenceError:
        return
    if key in _PENDING_STATE_REFRESHES:
        return
    _PENDING_STATE_REFRESHES.add(key)

    def refresh():
        try:
            if root.name in bpy.data.objects and hasattr(root, "spx_morph_states"):
                if _morph_state_structure_is_current(root):
                    _refresh_morph_state_metadata(root)
                else:
                    ensure_morph_states(root)
        except ReferenceError:
            pass
        finally:
            _PENDING_STATE_REFRESHES.discard(key)
            _tag_view3d_redraw()
        return None

    bpy.app.timers.register(refresh, first_interval=0.0)


def ensure_morph_states(root):
    global _MUTATING
    if root is None or not hasattr(root, "spx_morph_states"):
        return False
    old_uids = [state.uid for state in root.spx_morph_states]
    used = set()
    ordered = []
    for morph_type, morph in _ordered_morphs(root):
        uid = _ensure_morph_uid(morph, used)
        ordered.append((uid, morph_type, morph))

    states = root.spx_morph_states
    _MUTATING = True
    try:
        live_uids = {uid for uid, _morph_type, _morph in ordered}
        for index in reversed(range(len(states))):
            if states[index].uid not in live_uids:
                states.remove(index)
        for uid, morph_type, morph in ordered:
            state = states.get(uid)
            if state is None:
                state = states.add()
                state.name = uid
                state.uid = uid
                state.value = 0.0
            if state.morph_type != morph_type:
                state.morph_type = morph_type
            if state.morph_name != morph.name:
                state.morph_name = morph.name
        for target_index, (uid, _morph_type, _morph) in enumerate(ordered):
            current_index = states.find(uid)
            if current_index >= 0 and current_index != target_index:
                states.move(current_index, target_index)
    finally:
        _MUTATING = False
    return _remap_morph_state_animation_paths(root, old_uids)


def _effective_weights(root, morph_lookup):
    weights = {}
    states_by_uid = {state.uid: state for state in root.spx_morph_states}
    morph_keys = {}
    for state in root.spx_morph_states:
        morph = morph_lookup.get((state.morph_type, state.uid))
        if morph is None:
            continue
        key = (state.morph_type, state.uid)
        morph_keys[(state.morph_type, morph.name)] = key
        if state.morph_type != "group_morphs":
            weights[key] = float(state.value)

    def expand_group(state, factor, path):
        if state.uid in path:
            return
        morph = morph_lookup.get(("group_morphs", state.uid))
        if morph is None:
            return
        next_path = path | {state.uid}
        for offset in morph.data:
            target_key = morph_keys.get((offset.morph_type, offset.name))
            if target_key is None:
                continue
            contribution = factor * float(offset.factor)
            if target_key[0] == "group_morphs":
                target_state = states_by_uid.get(target_key[1])
                if target_state is not None:
                    expand_group(target_state, contribution, next_path)
            else:
                weights[target_key] = weights.get(target_key, 0.0) + contribution

    for state in root.spx_morph_states:
        if state.morph_type == "group_morphs" and abs(state.value) > 1.0e-8:
            expand_group(state, float(state.value), set())
    return weights


def _bound_placeholder(root):
    try:
        _FnModel, Model = _mmd_api()
        return Model(root).morph_slider.placeholder(binded=True)
    except (ImportError, RuntimeError, AttributeError):
        return None


def _remove_official_material_bindings(root):
    if bool(root.get(MATERIAL_BINDINGS_CLEAN_PROPERTY, False)):
        return
    try:
        _FnModel, Model = _mmd_api()
        shader_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.shader"
        )
    except ImportError:
        return
    materials = {material for material in Model(root).materials() if material}
    for material in tuple(materials):
        edge = bpy.data.materials.get("mmd_edge." + material.name)
        if edge is not None:
            materials.add(edge)
    for material in materials:
        if material.node_tree is None:
            continue
        nodes = material.node_tree.nodes
        targets = sorted(
            (node for node in nodes if node.name.startswith("mmd_bind")),
            key=lambda node: -node.location.x,
        )
        for node in targets:
            shader_module._MaterialMorph.reset_morph_links(node)
            nodes.remove(node)
    root[MATERIAL_BINDINGS_CLEAN_PROPERTY] = True


def _shape_key_driver_uses_object(key_block, target_object):
    animation_data = getattr(key_block.id_data, "animation_data", None)
    if animation_data is None:
        return False
    data_path = key_block.path_from_id("value")
    curve = next(
        (driver for driver in animation_data.drivers if driver.data_path == data_path),
        None,
    )
    if curve is None:
        return False
    return any(
        target.id == target_object
        for variable in curve.driver.variables
        for target in variable.targets
    )


def _remove_official_vertex_bindings(root):
    if bool(root.get(VERTEX_BINDINGS_CLEAN_PROPERTY, False)):
        return
    placeholder = _bound_placeholder(root)
    if placeholder is None:
        root[VERTEX_BINDINGS_CLEAN_PROPERTY] = True
        return
    FnModel, _Model = _mmd_api()
    vertex_names = {
        morph.name for morph in _morph_collection(root, "vertex_morphs")
    }
    for mesh_object in FnModel.iterate_mesh_objects(root):
        shape_keys = getattr(mesh_object.data, "shape_keys", None)
        if shape_keys is None:
            continue
        for key_block in reversed(tuple(shape_keys.key_blocks)):
            if (
                key_block.name.startswith("mmd_bind")
                and key_block.relative_key is not None
                and key_block.relative_key.name in vertex_names
                and _shape_key_driver_uses_object(key_block, placeholder)
            ):
                key_block.relative_key.mute = False
                key_block.driver_remove("value")
                mesh_object.shape_key_remove(key_block)
                continue
            if (
                key_block.name in vertex_names
                and _shape_key_driver_uses_object(key_block, placeholder)
            ):
                key_block.driver_remove("value")
                key_block.mute = False
    root[VERTEX_BINDINGS_CLEAN_PROPERTY] = True


def _remove_invalid_drivers(id_data):
    animation_data = getattr(id_data, "animation_data", None)
    if animation_data is None:
        return
    for curve in tuple(animation_data.drivers):
        try:
            id_data.path_resolve(curve.data_path)
        except ValueError:
            animation_data.drivers.remove(curve)


def _ensure_lightweight_bind(root, required_morph=None, force_rebind=False):
    _FnModel, Model = _mmd_api()
    slider = Model(root).morph_slider
    placeholder = _bound_placeholder(root)
    if (
        not force_rebind
        and placeholder is not None
        and bool(root.get(RUNTIME_BOUND_PROPERTY, False))
        and (required_morph is None or slider.get(required_morph.name) is not None)
    ):
        _remove_official_vertex_bindings(root)
        return
    missing_sliders = False
    if placeholder is not None:
        missing_sliders = any(
            slider.get(morph.name) is None
            for morph_type in MORPH_TYPE_KEYS
            for morph in _morph_collection(root, morph_type)
        )
    if not force_rebind and placeholder is not None and not missing_sliders:
        _remove_official_material_bindings(root)
        _remove_official_vertex_bindings(root)
        root[RUNTIME_BOUND_PROPERTY] = True
        return
    shader_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.shader"
    )
    descriptor = shader_module._MaterialMorph.__dict__["setup_morph_nodes"]

    def skip_material_nodes(_cls, _material, _morphs):
        return ()

    shader_module._MaterialMorph.setup_morph_nodes = classmethod(skip_material_nodes)
    root[VERTEX_BINDINGS_CLEAN_PROPERTY] = False
    try:
        slider.bind()
    finally:
        shader_module._MaterialMorph.setup_morph_nodes = descriptor
    if force_rebind:
        dummy_armature = slider.dummy_armature
        if dummy_armature is not None:
            _remove_invalid_drivers(dummy_armature)
    _remove_official_material_bindings(root)
    _remove_official_vertex_bindings(root)
    root[RUNTIME_BOUND_PROPERTY] = True


def _sync_placeholder_weights(root, weights, morph_lookup):
    placeholder = _bound_placeholder(root)
    if placeholder is None:
        return
    _FnModel, Model = _mmd_api()
    slider = Model(root).morph_slider
    for state in root.spx_morph_states:
        if state.morph_type not in {"bone_morphs", "uv_morphs"}:
            continue
        morph = morph_lookup.get((state.morph_type, state.uid))
        if morph is None:
            continue
        key_block = slider.get(morph.name)
        value = weights.get((state.morph_type, state.uid), 0.0)
        if key_block is None:
            continue
        if value < key_block.slider_min:
            key_block.slider_min = value
        if value > key_block.slider_max:
            key_block.slider_max = value
        if abs(key_block.value - value) > 1.0e-8:
            key_block.value = value


def _apply_vertex_values(root, weights, morph_lookup, state_uids=None):
    FnModel, _Model = _mmd_api()
    _remove_official_vertex_bindings(root)
    mesh_objects = tuple(FnModel.iterate_mesh_objects(root))
    for state in root.spx_morph_states:
        if state.morph_type != "vertex_morphs":
            continue
        if state_uids is not None and state.uid not in state_uids:
            continue
        morph = morph_lookup.get((state.morph_type, state.uid))
        if morph is None:
            continue
        value = weights.get((state.morph_type, state.uid), 0.0)
        for mesh_object in mesh_objects:
            shape_keys = getattr(mesh_object.data, "shape_keys", None)
            key_block = (
                shape_keys.key_blocks.get(morph.name)
                if shape_keys is not None
                else None
            )
            if key_block is None:
                continue
            animation_data = key_block.id_data.animation_data
            data_path = key_block.path_from_id("value")
            if animation_data is not None and any(
                curve.data_path == data_path
                for curve in animation_data.drivers
            ):
                continue
            if value < key_block.slider_min:
                key_block.slider_min = math.floor(value)
            if value > key_block.slider_max:
                key_block.slider_max = math.ceil(value)
            if abs(key_block.value - value) > 1.0e-8:
                key_block.value = value


def _ensure_material_uid(material):
    uid = str(material.get(MATERIAL_UID_PROPERTY, ""))
    if not uid:
        uid = uuid.uuid4().hex
        material[MATERIAL_UID_PROPERTY] = uid
    return uid


def _edge_materials(base_material):
    uid = _ensure_material_uid(base_material)
    result = []
    for material in bpy.data.materials:
        if str(material.get(EDGE_PARENT_UID_PROPERTY, "")) == uid:
            result.append(material)
    candidate = bpy.data.materials.get("mmd_edge." + base_material.name)
    if candidate is not None and candidate not in result:
        candidate[EDGE_PARENT_UID_PROPERTY] = uid
        result.append(candidate)
    return result


def _new_group_socket(node_group, name, in_out, socket_type):
    return node_group.interface.new_socket(
        name=name,
        in_out=in_out,
        socket_type=socket_type,
    )


def _output_group():
    node_group = bpy.data.node_groups.get(OUTPUT_GROUP_NAME)
    if node_group is not None:
        return node_group
    node_group = bpy.data.node_groups.new(OUTPUT_GROUP_NAME, "ShaderNodeTree")
    _new_group_socket(node_group, "Surface", "INPUT", "NodeSocketShader")
    opacity = _new_group_socket(
        node_group, "Opacity", "INPUT", "NodeSocketFloat"
    )
    opacity.default_value = 1.0
    opacity.min_value = 0.0
    opacity.max_value = 1.0
    tint = _new_group_socket(
        node_group, "Tint Color", "INPUT", "NodeSocketColor"
    )
    tint.default_value = (1.0, 1.0, 1.0, 1.0)
    tint_strength = _new_group_socket(
        node_group, "Tint Strength", "INPUT", "NodeSocketFloat"
    )
    tint_strength.default_value = 0.0
    tint_strength.min_value = 0.0
    tint_strength.max_value = 1.0
    add_color = _new_group_socket(
        node_group, "Add Color", "INPUT", "NodeSocketColor"
    )
    add_color.default_value = (0.0, 0.0, 0.0, 1.0)
    add_strength = _new_group_socket(
        node_group, "Add Strength", "INPUT", "NodeSocketFloat"
    )
    add_strength.default_value = 0.0
    add_strength.min_value = 0.0
    add_strength.max_value = 100.0
    _new_group_socket(node_group, "Surface", "OUTPUT", "NodeSocketShader")

    nodes = node_group.nodes
    links = node_group.links
    group_input = nodes.new("NodeGroupInput")
    group_input.location = (-700, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.location = (500, 0)
    tint_emission = nodes.new("ShaderNodeEmission")
    tint_emission.location = (-450, -180)
    links.new(group_input.outputs["Tint Color"], tint_emission.inputs["Color"])
    tint_mix = nodes.new("ShaderNodeMixShader")
    tint_mix.location = (-150, 80)
    links.new(group_input.outputs["Tint Strength"], tint_mix.inputs[0])
    links.new(group_input.outputs["Surface"], tint_mix.inputs[1])
    links.new(tint_emission.outputs[0], tint_mix.inputs[2])

    add_emission = nodes.new("ShaderNodeEmission")
    add_emission.location = (-150, -220)
    links.new(group_input.outputs["Add Color"], add_emission.inputs["Color"])
    links.new(group_input.outputs["Add Strength"], add_emission.inputs["Strength"])
    add_shader = nodes.new("ShaderNodeAddShader")
    add_shader.location = (50, 40)
    links.new(tint_mix.outputs[0], add_shader.inputs[0])
    links.new(add_emission.outputs[0], add_shader.inputs[1])

    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (0, 220)
    alpha_mix = nodes.new("ShaderNodeMixShader")
    alpha_mix.location = (280, 40)
    links.new(group_input.outputs["Opacity"], alpha_mix.inputs[0])
    links.new(transparent.outputs[0], alpha_mix.inputs[1])
    links.new(add_shader.outputs[0], alpha_mix.inputs[2])
    links.new(alpha_mix.outputs[0], group_output.inputs["Surface"])
    return node_group


def _ensure_output_bridges(material):
    material.use_nodes = True
    node_tree = material.node_tree
    if node_tree is None:
        return []
    group = _output_group()
    outputs = [
        node
        for node in node_tree.nodes
        if node.bl_idname == "ShaderNodeOutputMaterial"
        and node.inputs.get("Surface") is not None
        and node.inputs["Surface"].is_linked
    ]
    for output in outputs:
        source_link = output.inputs["Surface"].links[0]
        if bool(source_link.from_node.get(OUTPUT_BRIDGE_PROPERTY, False)):
            bridge = source_link.from_node
            if bridge.inputs["Surface"].is_linked:
                _normalize_upstream_alpha(
                    bridge.inputs["Surface"].links[0].from_node
                )
            continue
        source_socket = source_link.from_socket
        _normalize_upstream_alpha(source_link.from_node)
        node_tree.links.remove(source_link)
        bridge = node_tree.nodes.new("ShaderNodeGroup")
        bridge.node_tree = group
        bridge.name = OUTPUT_GROUP_NAME
        bridge.label = "Morph Output"
        bridge[OUTPUT_BRIDGE_PROPERTY] = True
        bridge.location = (output.location.x - 220, output.location.y)
        node_tree.links.new(source_socket, bridge.inputs["Surface"])
        node_tree.links.new(bridge.outputs["Surface"], output.inputs["Surface"])
    return [
        node
        for node in node_tree.nodes
        if node.bl_idname == "ShaderNodeGroup"
        and bool(node.get(OUTPUT_BRIDGE_PROPERTY, False))
    ]


def _normalize_upstream_alpha(source_node):
    alpha_socket = next(
        (
            socket
            for socket in source_node.inputs
            if socket.name.casefold() == "alpha" and not socket.is_linked
        ),
        None,
    )
    if alpha_socket is None:
        return
    try:
        current = float(alpha_socket.default_value)
    except (TypeError, ValueError):
        return
    if UPSTREAM_ALPHA_PROPERTY not in source_node:
        source_node[UPSTREAM_ALPHA_PROPERTY] = current
    if abs(current - 1.0) > 1.0e-7:
        alpha_socket.default_value = 1.0


def _set_socket(socket, value):
    current = socket.default_value
    if hasattr(current, "__len__"):
        if all(abs(float(a) - float(b)) <= 1.0e-7 for a, b in zip(current, value)):
            return
        socket.default_value = value
    elif abs(float(current) - float(value)) > 1.0e-7:
        socket.default_value = value


def _visual_parameters(effect):
    target = tuple(max(0.0, min(1.0, value)) for value in effect)
    tint_strength = max(abs(value - 1.0) for value in target)
    add = tuple(max(0.0, value - 1.0) for value in effect)
    add_strength = max(add)
    if add_strength > 1.0e-8:
        add_color = tuple(value / add_strength for value in add)
    else:
        add_color = (0.0, 0.0, 0.0)
    return target, min(1.0, tint_strength), add_color, add_strength


def _existing_output_bridges(material):
    return [
        node
        for node in getattr(getattr(material, "node_tree", None), "nodes", ())
        if bool(node.get(OUTPUT_BRIDGE_PROPERTY, False))
    ]


def _update_material_bridge(material, opacity, effect, install=True):
    bridges = (
        _ensure_output_bridges(material)
        if install
        else _existing_output_bridges(material)
    )
    tint, tint_strength, add_color, add_strength = _visual_parameters(effect)
    for bridge in bridges:
        _set_socket(bridge.inputs["Opacity"], max(0.0, min(1.0, opacity)))
        _set_socket(bridge.inputs["Tint Color"], (*tint, 1.0))
        _set_socket(bridge.inputs["Tint Strength"], tint_strength)
        _set_socket(bridge.inputs["Add Color"], (*add_color, 1.0))
        _set_socket(bridge.inputs["Add Strength"], add_strength)


def _model_materials(root):
    FnModel, _Model = _mmd_api()
    result = []
    seen = set()
    for mesh_object in FnModel.iterate_mesh_objects(root):
        for slot in mesh_object.material_slots:
            material = slot.material
            if material is None or material in seen:
                continue
            if material.name.startswith("mmd_edge.") or str(
                material.get(EDGE_PARENT_UID_PROPERTY, "")
            ):
                continue
            seen.add(material)
            result.append(material)
    return result


def _material_targets(materials, offset):
    material = getattr(offset, "material_data", None)
    if material is not None and material in materials:
        return (material,)
    name = str(getattr(offset, "material", ""))
    if not name:
        return tuple(materials)
    return tuple(material for material in materials if material.name == name)


def _neutral_accumulator():
    return {
        "opacity_mult": 1.0,
        "opacity_add": 0.0,
        "effect_mult": [1.0, 1.0, 1.0],
        "effect_add": [0.0, 0.0, 0.0],
        "edge_opacity_mult": 1.0,
        "edge_opacity_add": 0.0,
        "edge_effect_mult": [1.0, 1.0, 1.0],
        "edge_effect_add": [0.0, 0.0, 0.0],
    }


def _apply_material_values(root, weights, morph_lookup):
    materials = _model_materials(root)
    accumulators = {}
    for state in root.spx_morph_states:
        if state.morph_type != "material_morphs":
            continue
        weight = weights.get((state.morph_type, state.uid), 0.0)
        if abs(weight) <= 1.0e-8:
            continue
        morph = morph_lookup.get((state.morph_type, state.uid))
        if morph is None:
            continue
        for offset in morph.data:
            for material in _material_targets(materials, offset):
                values = accumulators.setdefault(material, _neutral_accumulator())
                if offset.offset_type == "MULT":
                    values["opacity_mult"] *= 1.0 + (
                        float(offset.diffuse_color[3]) - 1.0
                    ) * weight
                    values["edge_opacity_mult"] *= 1.0 + (
                        float(offset.edge_color[3]) - 1.0
                    ) * weight
                    for index in range(3):
                        values["effect_mult"][index] *= 1.0 + (
                            float(offset.diffuse_color[index]) - 1.0
                        ) * weight
                        values["edge_effect_mult"][index] *= 1.0 + (
                            float(offset.edge_color[index]) - 1.0
                        ) * weight
                else:
                    values["opacity_add"] += float(offset.diffuse_color[3]) * weight
                    values["edge_opacity_add"] += float(offset.edge_color[3]) * weight
                    for index in range(3):
                        values["effect_add"][index] += (
                            float(offset.diffuse_color[index]) * weight
                        )
                        values["edge_effect_add"][index] += (
                            float(offset.edge_color[index]) * weight
                        )

    if accumulators:
        _remove_official_material_bindings(root)
    for material, values in accumulators.items():
        mmd_material = getattr(material, "mmd_material", None)
        base_opacity = float(
            getattr(mmd_material, "alpha", material.diffuse_color[3])
        )
        body_opacity = max(
            0.0,
            min(
                1.0,
                base_opacity * values["opacity_mult"] + values["opacity_add"],
            ),
        )
        body_effect = tuple(
            values["effect_mult"][index] + values["effect_add"][index]
            for index in range(3)
        )
        edge_color = getattr(mmd_material, "edge_color", (0.0, 0.0, 0.0, 1.0))
        base_edge_opacity = float(edge_color[3])
        edge_opacity = max(
            0.0,
            min(
                1.0,
                base_edge_opacity * values["edge_opacity_mult"]
                + values["edge_opacity_add"],
            ),
        )
        edge_effect = tuple(
            values["edge_effect_mult"][index]
            + values["edge_effect_add"][index]
            for index in range(3)
        )
        _update_material_bridge(material, body_opacity, body_effect)
        edge_changed = abs(edge_opacity - 1.0) > 1.0e-7 or any(
            abs(value - 1.0) > 1.0e-7 for value in edge_effect
        )
        for edge_material in _edge_materials(material):
            _update_material_bridge(
                edge_material,
                edge_opacity,
                edge_effect,
                install=edge_changed,
            )

    # Existing bridges must return to their neutral state when all sliders reset.
    for material in materials:
        if material in accumulators:
            continue
        mmd_material = getattr(material, "mmd_material", None)
        base_opacity = float(
            getattr(mmd_material, "alpha", material.diffuse_color[3])
        )
        bridges = _existing_output_bridges(material)
        if bridges:
            _update_material_bridge(
                material,
                base_opacity,
                (1.0, 1.0, 1.0),
            )
        edge_color = getattr(mmd_material, "edge_color", (0.0, 0.0, 0.0, 1.0))
        base_edge_opacity = float(edge_color[3])
        for edge_material in _edge_materials(material):
            edge_bridges = _existing_output_bridges(edge_material)
            if edge_bridges:
                _update_material_bridge(
                    edge_material,
                    base_edge_opacity,
                    (1.0, 1.0, 1.0),
                )


def evaluate_morph_root(root, changed_type=None, changed_uid=None):
    global _EVALUATING
    if _EVALUATING or root is None:
        return
    _EVALUATING = True
    try:
        if changed_type is None and not _morph_states_are_current(root):
            ensure_morph_states(root)
        morph_lookup = _morph_lookup(root)
        changed_state = next(
            (state for state in root.spx_morph_states if state.uid == changed_uid),
            None,
        )

        if changed_type == "material_morphs":
            weights = _effective_weights(root, morph_lookup)
            _apply_material_values(root, weights, morph_lookup)
        elif changed_type == "vertex_morphs":
            weights = _effective_weights(root, morph_lookup)
            _apply_vertex_values(
                root,
                weights,
                morph_lookup,
                {changed_uid} if changed_uid else None,
            )
        elif changed_type in {"bone_morphs", "uv_morphs"}:
            required_morph = (
                morph_lookup.get((changed_state.morph_type, changed_state.uid))
                if changed_state is not None
                else None
            )
            _ensure_lightweight_bind(root, required_morph)
            morph_lookup = _morph_lookup(root)
            weights = _effective_weights(root, morph_lookup)
            _sync_placeholder_weights(root, weights, morph_lookup)
        elif changed_type == "group_morphs":
            weights = _effective_weights(root, morph_lookup)
            needs_runtime = any(
                morph_type in {"bone_morphs", "uv_morphs"}
                and abs(value) > 1.0e-8
                for (morph_type, _uid), value in weights.items()
            )
            runtime_exists = (
                _bound_placeholder(root) is not None
                and bool(root.get(RUNTIME_BOUND_PROPERTY, False))
            )
            if needs_runtime:
                _ensure_lightweight_bind(root)
                morph_lookup = _morph_lookup(root)
                weights = _effective_weights(root, morph_lookup)
                runtime_exists = True
            if runtime_exists:
                _sync_placeholder_weights(root, weights, morph_lookup)
            _apply_vertex_values(root, weights, morph_lookup)
            _apply_material_values(root, weights, morph_lookup)
        else:
            weights = _effective_weights(root, morph_lookup)
            needs_runtime = any(
                morph_type in {"bone_morphs", "uv_morphs"}
                and abs(value) > 1.0e-8
                for (morph_type, _uid), value in weights.items()
            )
            runtime_exists = (
                _bound_placeholder(root) is not None
                and bool(root.get(RUNTIME_BOUND_PROPERTY, False))
            )
            if needs_runtime:
                _ensure_lightweight_bind(root)
                morph_lookup = _morph_lookup(root)
                weights = _effective_weights(root, morph_lookup)
                runtime_exists = True
            if runtime_exists:
                _sync_placeholder_weights(root, weights, morph_lookup)
            _apply_vertex_values(root, weights, morph_lookup)
            _apply_material_values(root, weights, morph_lookup)
        if RUNTIME_ERROR_PROPERTY in root:
            del root[RUNTIME_ERROR_PROPERTY]
    except Exception as error:
        root[RUNTIME_ERROR_PROPERTY] = str(error)
    finally:
        _EVALUATING = False


def _morph_value_updated(state, _context):
    if _MUTATING:
        return
    root = state.id_data
    if root is not None and getattr(root, "mmd_type", "") == "ROOT":
        evaluate_morph_root(root, state.morph_type, state.uid)


def _animation_placeholder(root):
    try:
        _FnModel, Model = _mmd_api()
        return Model(root).morph_slider.placeholder()
    except (ImportError, RuntimeError, AttributeError):
        return None


def _shape_key_action_paths(shape_keys):
    return {
        key_block.path_from_id("value"): key_block.name
        for key_block in shape_keys.key_blocks[1:]
    }


def _morph_state_data_path(state):
    return state.path_from_id("value")


_MORPH_STATE_INDEX_PATH = re.compile(r"^spx_morph_states\[(\d+)\]\.value$")
_MORPH_STATE_UID_PATH = re.compile(
    r'^spx_morph_states\["([0-9a-f]+)"\]\.value$'
)


def _copy_keyframe_point(source, destination):
    destination.co = source.co
    destination.interpolation = source.interpolation
    destination.easing = source.easing
    destination.type = source.type
    destination.amplitude = source.amplitude
    destination.back = source.back
    destination.period = source.period
    destination.handle_left_type = source.handle_left_type
    destination.handle_right_type = source.handle_right_type
    destination.handle_left = source.handle_left
    destination.handle_right = source.handle_right


def _merge_fcurve_points(source, destination):
    by_frame = {
        round(float(point.co.x), 6): point
        for point in destination.keyframe_points
    }
    for source_point in source.keyframe_points:
        frame_key = round(float(source_point.co.x), 6)
        destination_point = by_frame.get(frame_key)
        if destination_point is None:
            destination_point = destination.keyframe_points.insert(
                source_point.co.x,
                source_point.co.y,
                options={"FAST"},
            )
            by_frame[frame_key] = destination_point
        _copy_keyframe_point(source_point, destination_point)
    destination.update()


def _remap_morph_state_animation_paths(root, old_uids):
    animation_data = root.animation_data
    if animation_data is None:
        return False
    new_index_by_uid = {
        state.uid: index for index, state in enumerate(root.spx_morph_states)
    }
    changed = False
    for action in tuple(_iter_animation_actions(animation_data) or ()):
        grouped = {}
        for curve in tuple(action.fcurves):
            uid = None
            index_match = _MORPH_STATE_INDEX_PATH.fullmatch(curve.data_path)
            if index_match is not None:
                old_index = int(index_match.group(1))
                if 0 <= old_index < len(old_uids):
                    uid = old_uids[old_index]
            else:
                uid_match = _MORPH_STATE_UID_PATH.fullmatch(curve.data_path)
                if uid_match is not None:
                    uid = uid_match.group(1)
            new_index = new_index_by_uid.get(uid)
            if new_index is None:
                continue
            target_path = f"spx_morph_states[{new_index}].value"
            grouped.setdefault(target_path, []).append(curve)

        for target_path, curves in grouped.items():
            canonical = next(
                (
                    curve
                    for curve in curves
                    if _MORPH_STATE_UID_PATH.fullmatch(curve.data_path)
                ),
                curves[0],
            )
            for curve in curves:
                if curve is canonical:
                    continue
                _merge_fcurve_points(curve, canonical)
                action.fcurves.remove(curve)
                changed = True
            if canonical.data_path != target_path:
                canonical.data_path = target_path
                changed = True
    return changed


def _iter_animation_actions(animation_data):
    if animation_data is None:
        return
    seen = set()
    action = animation_data.action
    if action is not None:
        seen.add(action.as_pointer())
        yield action
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            action = strip.action
            if action is None or action.as_pointer() in seen:
                continue
            seen.add(action.as_pointer())
            yield action


def _morph_curves(action, path_names, state_by_name):
    result = []
    for curve in tuple(action.fcurves):
        morph_name = path_names.get(curve.data_path)
        state = state_by_name.get(morph_name)
        if state is not None:
            result.append((curve, state))
    return result


def _copy_fcurve(source, destination_action, data_path):
    destination = destination_action.fcurves.find(data_path, index=source.array_index)
    if destination is None:
        destination = destination_action.fcurves.new(
            data_path,
            index=source.array_index,
            action_group="Morph",
        )
    original_count = len(destination.keyframe_points)
    destination.keyframe_points.add(len(source.keyframe_points))
    for source_point, destination_point in zip(
        source.keyframe_points,
        destination.keyframe_points[original_count:],
        strict=False,
    ):
        _copy_keyframe_point(source_point, destination_point)
    destination.extrapolation = source.extrapolation
    if original_count == 0 and not destination.modifiers:
        for source_modifier in source.modifiers:
            destination_modifier = destination.modifiers.new(source_modifier.type)
            for prop in source_modifier.bl_rna.properties:
                if prop.identifier in {"rna_type", "type"} or prop.is_readonly:
                    continue
                try:
                    setattr(
                        destination_modifier,
                        prop.identifier,
                        getattr(source_modifier, prop.identifier),
                    )
                except (AttributeError, TypeError, ValueError):
                    pass
    destination.update()


def _copy_nla_strip(source_strip, destination_track, destination_action):
    strip = destination_track.strips.new(
        source_strip.name + ".spx_morph",
        round(source_strip.frame_start),
        destination_action,
    )
    for attribute in (
        "action_frame_start",
        "action_frame_end",
        "blend_in",
        "blend_out",
        "blend_type",
        "extrapolation",
        "influence",
        "repeat",
        "scale",
        "use_auto_blend",
        "use_reverse",
        "use_sync_length",
    ):
        try:
            setattr(strip, attribute, getattr(source_strip, attribute))
        except (AttributeError, TypeError, ValueError):
            pass
    strip.frame_start = source_strip.frame_start
    strip.frame_end = source_strip.frame_end
    return strip


def _ensure_root_action(root, source_action):
    animation_data = root.animation_data_create()
    return animation_data.action or bpy.data.actions.new(
        name=source_action.name + ".spx_morph"
    )


def _migrate_placeholder_animation(root, skip_existing=False):
    placeholder = _animation_placeholder(root)
    if placeholder is None or placeholder.data.shape_keys is None:
        return set()
    ensure_morph_states(root)
    state_by_name = {}
    for state in root.spx_morph_states:
        state_by_name.setdefault(state.morph_name, state)
    existing_uids = set()
    if skip_existing:
        state_by_path = {
            _morph_state_data_path(state): state for state in root.spx_morph_states
        }
        for action in tuple(_iter_animation_actions(root.animation_data) or ()):
            for curve in action.fcurves:
                state = state_by_path.get(curve.data_path)
                if state is not None:
                    existing_uids.add(state.uid)
    shape_keys = placeholder.data.shape_keys
    animation_data = shape_keys.animation_data
    if animation_data is None:
        return set()
    path_names = _shape_key_action_paths(shape_keys)
    imported_uids = set()
    active_action = animation_data.action
    if active_action is not None:
        curves = [
            (curve, state)
            for curve, state in _morph_curves(
                active_action,
                path_names,
                state_by_name,
            )
            if not skip_existing or state.uid not in existing_uids
        ]
        if curves:
            destination_action = _ensure_root_action(root, active_action)
            for curve, state in curves:
                _copy_fcurve(curve, destination_action, _morph_state_data_path(state))
                imported_uids.add(state.uid)
                if skip_existing:
                    existing_uids.add(state.uid)
            if root.animation_data.action is None:
                root.animation_data.action = destination_action

    destination_actions = {}
    for source_track in animation_data.nla_tracks:
        destination_track = None
        for source_strip in source_track.strips:
            source_action = source_strip.action
            if source_action is None:
                continue
            curves = [
                (curve, state)
                for curve, state in _morph_curves(
                    source_action,
                    path_names,
                    state_by_name,
                )
                if not skip_existing or state.uid not in existing_uids
            ]
            if not curves:
                continue
            destination_action = destination_actions.get(source_action.as_pointer())
            if destination_action is None:
                destination_action = bpy.data.actions.new(
                    name=source_action.name + ".spx_morph"
                )
                destination_actions[source_action.as_pointer()] = destination_action
                for curve, state in curves:
                    _copy_fcurve(
                        curve,
                        destination_action,
                        _morph_state_data_path(state),
                    )
                    imported_uids.add(state.uid)
                    if skip_existing:
                        existing_uids.add(state.uid)
            if destination_track is None:
                destination_track = root.animation_data_create().nla_tracks.new()
                destination_track.name = source_track.name + ".spx_morph"
            _copy_nla_strip(source_strip, destination_track, destination_action)
    return imported_uids


def _remove_imported_shape_key_curves(root):
    FnModel, _Model = _mmd_api()
    objects = list(FnModel.iterate_mesh_objects(root))
    placeholder = _animation_placeholder(root)
    if placeholder is not None:
        objects.append(placeholder)
    morph_names = {state.morph_name for state in root.spx_morph_states}
    for mesh_object in objects:
        shape_keys = getattr(mesh_object.data, "shape_keys", None)
        if shape_keys is None:
            continue
        path_names = _shape_key_action_paths(shape_keys)
        animation_data = shape_keys.animation_data
        for action in tuple(_iter_animation_actions(animation_data) or ()):
            for curve in tuple(action.fcurves):
                if path_names.get(curve.data_path) in morph_names:
                    action.fcurves.remove(curve)


def _expanded_import_targets(root, imported_uids):
    state_by_uid = {state.uid: state for state in root.spx_morph_states}
    keys_by_name = {
        (state.morph_type, state.morph_name): (state.morph_type, state.uid)
        for state in root.spx_morph_states
    }
    targets = set()

    def expand(key, path):
        if key in path or key in targets:
            return
        targets.add(key)
        if key[0] != "group_morphs":
            return
        morph = _morph_by_uid(root, *key)
        if morph is None:
            return
        next_path = path | {key}
        for offset in morph.data:
            target = keys_by_name.get((offset.morph_type, offset.name))
            if target is not None:
                expand(target, next_path)

    for uid in imported_uids:
        state = state_by_uid.get(uid)
        if state is not None:
            expand((state.morph_type, state.uid), set())
    return targets


def _edge_offset_changes_output(offset):
    neutral = 1.0 if offset.offset_type == "MULT" else 0.0
    return any(abs(float(value) - neutral) > 1.0e-8 for value in offset.edge_color)


def _preinitialize_imported_morphs(root, imported_uids):
    targets = _expanded_import_targets(root, imported_uids)
    if any(key[0] in {"bone_morphs", "uv_morphs"} for key in targets):
        _ensure_lightweight_bind(root)
        ensure_morph_states(root)
    materials = _model_materials(root)
    for morph_type, uid in targets:
        if morph_type != "material_morphs":
            continue
        morph = _morph_by_uid(root, morph_type, uid)
        if morph is None:
            continue
        for offset in morph.data:
            for material in _material_targets(materials, offset):
                _ensure_output_bridges(material)
                if _edge_offset_changes_output(offset):
                    for edge_material in _edge_materials(material):
                        _ensure_output_bridges(edge_material)


def _prepare_vmd_import(context):
    FnModel, Model = _mmd_api()
    roots = []
    placeholders = []
    seen = set()
    for obj in tuple(context.selected_objects):
        root = FnModel.find_root_object(obj)
        if root is None or root.as_pointer() in seen:
            continue
        if obj != root and obj.type != "MESH":
            continue
        seen.add(root.as_pointer())
        ensure_morph_states(root)
        placeholder = Model(root).morph_slider.create()
        ensure_morph_states(root)
        roots.append(root)
        placeholders.append(placeholder)
    return roots, placeholders


def _import_vmd_execute(operator, context):
    global _MUTATING
    original_selection = tuple(context.selected_objects)
    original_active = context.view_layer.objects.active
    roots = []
    try:
        roots, placeholders = _prepare_vmd_import(context)
        for placeholder in placeholders:
            placeholder.select_set(True)
        result = _ORIGINAL_IMPORT_VMD_EXECUTE(operator, context)
        for root in roots:
            try:
                imported_uids = _migrate_placeholder_animation(root)
                _remove_imported_shape_key_curves(root)
                _preinitialize_imported_morphs(root, imported_uids)
                if getattr(operator, "create_new_action", False):
                    _MUTATING = True
                    try:
                        animated = set(imported_uids)
                        for state in root.spx_morph_states:
                            if state.uid not in animated:
                                state.value = 0.0
                    finally:
                        _MUTATING = False
            except Exception as error:
                root[RUNTIME_ERROR_PROPERTY] = f"VMD Morph 初始化失败: {error}"
        if roots:
            _MUTATING = True
            try:
                context.scene.frame_set(context.scene.frame_current)
            finally:
                _MUTATING = False
            for root in roots:
                evaluate_morph_root(root)
        return result
    finally:
        for obj in tuple(context.selected_objects):
            obj.select_set(False)
        for obj in original_selection:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active is not None and original_active.name in bpy.data.objects:
            context.view_layer.objects.active = original_active


def _migrate_existing_vmd_morph_animations():
    migrated = {}
    changed_roots = set()
    for root in tuple(bpy.data.objects):
        if getattr(root, "mmd_type", "") != "ROOT" or not hasattr(
            root,
            "spx_morph_states",
        ):
            continue
        try:
            if ensure_morph_states(root):
                changed_roots.add(root.name)
            imported_uids = _migrate_placeholder_animation(
                root,
                skip_existing=True,
            )
            if not imported_uids:
                continue
            _remove_imported_shape_key_curves(root)
            _preinitialize_imported_morphs(root, imported_uids)
            migrated[root.name] = imported_uids
            changed_roots.add(root.name)
        except Exception as error:
            root[RUNTIME_ERROR_PROPERTY] = f"现有 VMD Morph 接管失败: {error}"
    if changed_roots:
        scene = bpy.context.scene
        if scene is not None:
            global _MUTATING
            _MUTATING = True
            try:
                scene.frame_set(scene.frame_current)
            finally:
                _MUTATING = False
        for root_name in changed_roots:
            root = bpy.data.objects.get(root_name)
            if root is not None:
                evaluate_morph_root(root)
        _tag_view3d_redraw()
    return migrated


def _migrate_existing_vmd_morph_animations_timer():
    _migrate_existing_vmd_morph_animations()
    return None


@persistent
def _migrate_existing_vmd_morph_animations_on_load(_dummy):
    if not bpy.app.timers.is_registered(
        _migrate_existing_vmd_morph_animations_timer
    ):
        bpy.app.timers.register(
            _migrate_existing_vmd_morph_animations_timer,
            first_interval=0.0,
        )


def _vmd_export_morph_curves(root):
    animation_data = root.animation_data
    action = animation_data.action if animation_data is not None else None
    if action is None:
        return []
    states_by_path = {
        _morph_state_data_path(state): state for state in root.spx_morph_states
    }
    curves = []
    used_names = set()
    for curve in action.fcurves:
        state = states_by_path.get(curve.data_path)
        if state is None or not state.morph_name or state.morph_name in used_names:
            continue
        used_names.add(state.morph_name)
        curves.append((curve, state))
    return curves


@contextmanager
def _vmd_export_morph_bridge(context):
    active_object = context.active_object
    if active_object is None or active_object.type == "ARMATURE":
        yield
        return
    FnModel, Model = _mmd_api()
    root = FnModel.find_root_object(active_object)
    if root is None or not hasattr(root, "spx_morph_states"):
        yield
        return
    ensure_morph_states(root)
    curves = _vmd_export_morph_curves(root)
    if not curves:
        yield
        return

    created_placeholder = False
    added_shape_keys = []
    previous_action = None
    previous_basis_mute = None
    had_animation_data = False
    target_had_shape_keys = True
    temporary_action = None
    target = None
    try:
        if active_object == root:
            existing_placeholder = next(
                (
                    child
                    for child in root.children
                    if child.mmd_type == "PLACEHOLDER" and child.type == "MESH"
                ),
                None,
            )
            existing_shape_keys = (
                existing_placeholder.data.shape_keys
                if existing_placeholder is not None
                else None
            )
            target_had_shape_keys = existing_shape_keys is not None
            existing_key_names = (
                set(existing_shape_keys.key_blocks.keys())
                if existing_shape_keys is not None
                else set()
            )
            target = Model(root).morph_slider.create()
            created_placeholder = existing_placeholder is None
            if not created_placeholder and target_had_shape_keys:
                added_shape_keys.extend(
                    key_block
                    for key_block in target.data.shape_keys.key_blocks
                    if key_block.name not in existing_key_names
                )
        elif active_object.type == "MESH":
            target = active_object
            target_had_shape_keys = target.data.shape_keys is not None
        if target is None:
            yield
            return

        shape_keys = target.data.shape_keys
        if shape_keys is None:
            target.shape_key_add(name="Basis", from_mix=False)
            shape_keys = target.data.shape_keys
        for _curve, state in curves:
            if state.morph_name not in shape_keys.key_blocks:
                added_shape_keys.append(
                    target.shape_key_add(name=state.morph_name, from_mix=False)
                )

        basis = shape_keys.key_blocks[0]
        previous_basis_mute = basis.mute
        basis.mute = False
        had_animation_data = shape_keys.animation_data is not None
        animation_data = shape_keys.animation_data_create()
        previous_action = animation_data.action
        temporary_action = bpy.data.actions.new(".MMD Station VMD Export Morph")
        for curve, state in curves:
            key_block = shape_keys.key_blocks.get(state.morph_name)
            if key_block is not None:
                _copy_fcurve(
                    curve,
                    temporary_action,
                    key_block.path_from_id("value"),
                )
        animation_data.action = temporary_action
        yield
    finally:
        if target is not None and target.data.shape_keys is not None:
            shape_keys = target.data.shape_keys
            animation_data = shape_keys.animation_data
            if animation_data is not None and animation_data.action == temporary_action:
                animation_data.action = previous_action
            if previous_basis_mute is not None and shape_keys.key_blocks:
                shape_keys.key_blocks[0].mute = previous_basis_mute
            if (
                not had_animation_data
                and shape_keys.animation_data is not None
                and shape_keys.animation_data.action is None
                and not shape_keys.animation_data.drivers
                and not shape_keys.animation_data.nla_tracks
            ):
                shape_keys.animation_data_clear()
            if not created_placeholder and not target_had_shape_keys:
                target.shape_key_clear()
            elif not created_placeholder:
                for key_block in reversed(added_shape_keys):
                    if key_block.name in shape_keys.key_blocks:
                        target.shape_key_remove(shape_keys.key_blocks[key_block.name])
        if temporary_action is not None:
            bpy.data.actions.remove(temporary_action)
        if created_placeholder and target is not None and target.name in bpy.data.objects:
            mesh = target.data
            bpy.data.objects.remove(target, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def _export_vmd_execute(operator, context):
    with _vmd_export_morph_bridge(context):
        return _ORIGINAL_EXPORT_VMD_EXECUTE(operator, context)


def _install_vmd_io_hooks():
    global _ORIGINAL_IMPORT_VMD_EXECUTE, _IMPORT_VMD_CLASS
    global _ORIGINAL_EXPORT_VMD_EXECUTE, _EXPORT_VMD_CLASS
    try:
        fileio = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.operators.fileio"
        )
    except ImportError:
        return 0.5
    if _ORIGINAL_IMPORT_VMD_EXECUTE is None:
        import_class = fileio.ImportVmd
        if import_class.execute is not _import_vmd_execute:
            _IMPORT_VMD_CLASS = import_class
            _ORIGINAL_IMPORT_VMD_EXECUTE = import_class.execute
            import_class.execute = _import_vmd_execute
    if _ORIGINAL_EXPORT_VMD_EXECUTE is None:
        export_class = fileio.ExportVmd
        if export_class.execute is not _export_vmd_execute:
            _EXPORT_VMD_CLASS = export_class
            _ORIGINAL_EXPORT_VMD_EXECUTE = export_class.execute
            export_class.execute = _export_vmd_execute
    return None


def _remove_vmd_io_hooks():
    global _ORIGINAL_IMPORT_VMD_EXECUTE, _IMPORT_VMD_CLASS
    global _ORIGINAL_EXPORT_VMD_EXECUTE, _EXPORT_VMD_CLASS
    if (
        _IMPORT_VMD_CLASS is not None
        and _ORIGINAL_IMPORT_VMD_EXECUTE is not None
        and _IMPORT_VMD_CLASS.execute is _import_vmd_execute
    ):
        _IMPORT_VMD_CLASS.execute = _ORIGINAL_IMPORT_VMD_EXECUTE
    _ORIGINAL_IMPORT_VMD_EXECUTE = None
    _IMPORT_VMD_CLASS = None
    if (
        _EXPORT_VMD_CLASS is not None
        and _ORIGINAL_EXPORT_VMD_EXECUTE is not None
        and _EXPORT_VMD_CLASS.execute is _export_vmd_execute
    ):
        _EXPORT_VMD_CLASS.execute = _ORIGINAL_EXPORT_VMD_EXECUTE
    _ORIGINAL_EXPORT_VMD_EXECUTE = None
    _EXPORT_VMD_CLASS = None


def _sync_official_active_morph(root):
    if root is None or not (0 <= root.spx_morph_active_index < len(root.spx_morph_states)):
        return
    state = root.spx_morph_states[root.spx_morph_active_index]
    if state.morph_type not in MORPH_TYPE_KEYS:
        return
    morphs = _morph_collection(root, state.morph_type)
    morph_index = next(
        (
            index
            for index, morph in enumerate(morphs)
            if str(morph.get(MORPH_UID_PROPERTY, "")) == state.uid
        ),
        -1,
    )
    if morph_index < 0:
        return
    root.mmd_root.active_morph_type = state.morph_type
    root.mmd_root.active_morph = morph_index


def _active_morph_index_updated(root, _context):
    if not _MUTATING:
        _sync_official_active_morph(root)


def _morph_editor_type_updated(settings, _context):
    root = settings.morph_editor_root
    if root is None or not hasattr(root, "spx_morph_states"):
        return
    for index, state in enumerate(root.spx_morph_states):
        if state.morph_type == settings.morph_editor_type:
            root.spx_morph_active_index = index
            return


class SPX_MorphState(PropertyGroup):
    name: StringProperty()
    uid: StringProperty()
    morph_type: StringProperty()
    morph_name: StringProperty()
    selected: BoolProperty(name="选择", default=False)
    value: FloatProperty(
        name="Morph 值",
        description="统一驱动该 Morph；拖动范围为 0～1，点击数值可输入任意有符号值，也可直接插入 Keyframe",
        default=0.0,
        soft_min=0.0,
        soft_max=1.0,
        update=_morph_value_updated,
    )


class SPX_OT_SetMorphValue(Operator):
    bl_idname = "surface_proxy.set_morph_value"
    bl_label = "设置 Morph 值"
    bl_description = "将同一个 Morph 滑块直接切换到 0 或 1"
    bl_options = {"INTERNAL", "UNDO"}

    root_name: StringProperty(options={"HIDDEN"})
    morph_uid: StringProperty(options={"HIDDEN"})
    value: FloatProperty(options={"HIDDEN"})

    def execute(self, _context):
        root = bpy.data.objects.get(self.root_name)
        if root is None or not hasattr(root, "spx_morph_states"):
            return {"CANCELLED"}
        state = next(
            (state for state in root.spx_morph_states if state.uid == self.morph_uid),
            None,
        )
        if state is None:
            return {"CANCELLED"}
        state.value = self.value
        return {"FINISHED"}


class SPX_UL_MorphEditor(UIList):
    def filter_items(self, context, data, propname):
        states = getattr(data, propname)
        settings = context.scene.surface_proxy_creator
        search = settings.morph_editor_search.casefold().strip()
        flags = []
        for state in states:
            morph = _morph_by_uid(data, state.morph_type, state.uid)
            visible = state.morph_type == settings.morph_editor_type
            if visible and search and morph is not None:
                visible = search in f"{morph.name} {morph.name_e}".casefold()
            flags.append(self.bitflag_filter_item if visible else 0)
        return flags, []

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        morph = _morph_by_uid(data, item.morph_type, item.uid)
        if morph is None:
            layout.label(text="失效 Morph", icon="ERROR")
            return
        settings = context.scene.surface_proxy_creator
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        if settings.morph_editor_show_japanese:
            row.prop(morph, "name", text="", emboss=False, icon="SHAPEKEY_DATA")
        if settings.morph_editor_show_english:
            row.prop(morph, "name_e", text="")
        row.prop(morph, "category", text="", emboss=False)
        value_row = row.row(align=True)
        zero_button = value_row.row(align=True)
        zero_button.ui_units_x = 1.0
        operator = zero_button.operator(
            "surface_proxy.set_morph_value",
            text="0",
            depress=math.isclose(item.value, 0.0, abs_tol=1.0e-6),
        )
        operator.root_name = data.name
        operator.morph_uid = item.uid
        operator.value = 0.0
        slider_row = value_row.row(align=True)
        slider_row.use_property_decorate = True
        slider_row.prop(item, "value", text="", slider=True)
        one_button = value_row.row(align=True)
        one_button.ui_units_x = 1.0
        operator = one_button.operator(
            "surface_proxy.set_morph_value",
            text="1",
            depress=math.isclose(item.value, 1.0, abs_tol=1.0e-6),
        )
        operator.root_name = data.name
        operator.morph_uid = item.uid
        operator.value = 1.0


def _set_collection_order(collection, desired_names):
    for target_index, name in enumerate(desired_names):
        current_index = collection.find(name)
        if current_index >= 0 and current_index != target_index:
            collection.move(current_index, target_index)


def _sync_morph_order(root):
    states = root.spx_morph_states
    for morph_type in MORPH_TYPE_KEYS:
        uids = [state.uid for state in states if state.morph_type == morph_type]
        morphs = _morph_collection(root, morph_type)
        desired = []
        for uid in uids:
            morph = _morph_by_uid(root, morph_type, uid)
            if morph is not None:
                desired.append(morph.name)
        for target_index, name in enumerate(desired):
            current_index = morphs.find(name)
            if current_index >= 0 and current_index != target_index:
                morphs.move(current_index, target_index)


def _restore_missing_vertex_morphs(root):
    FnModel, _Model = _mmd_api()
    morph_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.morph"
    )
    morphs = root.mmd_root.vertex_morphs
    known_names = {morph.name for morph in morphs}
    restored = 0
    for mesh_object in FnModel.iterate_mesh_objects(root):
        shape_keys = getattr(mesh_object.data, "shape_keys", None)
        for key_block in getattr(shape_keys, "key_blocks", ())[1:]:
            name = key_block.name
            if name.startswith("mmd_") or name in known_names:
                continue
            morph = morphs.add()
            morph.name = name
            morph.name_e = name
            morph_module.FnMorph.category_guess(morph)
            known_names.add(name)
            restored += 1
    return restored


def _remove_vertex_morph_shape_keys(root, morph_names):
    FnModel, Model = _mmd_api()
    morph_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.morph"
    )
    mesh_objects = list(FnModel.iterate_mesh_objects(root))
    placeholder = Model(root).morph_slider.placeholder(create=False)
    if placeholder is not None:
        mesh_objects.append(placeholder)
    removed = 0
    for mesh_object in mesh_objects:
        key_blocks = getattr(
            getattr(mesh_object.data, "shape_keys", None),
            "key_blocks",
            (),
        )
        for morph_name in morph_names:
            if morph_name not in key_blocks:
                continue
            morph_module.FnMorph.remove_shape_key(mesh_object, morph_name)
            removed += 1
    return removed


def _uv_morph_vertex_groups(mesh_object, morph_name):
    prefix = f"UV_{morph_name}"
    valid_suffixes = {f"{sign}{axis}" for sign in "+-" for axis in "XYZW"}
    return tuple(
        group
        for group in mesh_object.vertex_groups
        if group.name.startswith(prefix)
        and group.name[len(prefix) :] in valid_suffixes
    )


def _remove_uv_morph_runtime_data(root, morph_names):
    FnModel, Model = _mmd_api()
    mesh_objects = tuple(FnModel.iterate_mesh_objects(root))
    removed = 0
    for mesh_object in mesh_objects:
        for morph_name in morph_names:
            for group in _uv_morph_vertex_groups(mesh_object, morph_name):
                for modifier in tuple(mesh_object.modifiers):
                    if (
                        modifier.type == "UV_WARP"
                        and modifier.vertex_group == group.name
                    ):
                        mesh_object.modifiers.remove(modifier)
                mesh_object.vertex_groups.remove(group)
                removed += 1

    placeholder = Model(root).morph_slider.placeholder(create=False)
    if placeholder is not None:
        for morph_name in morph_names:
            shape_keys = getattr(placeholder.data, "shape_keys", None)
            key_block = shape_keys.key_blocks.get(morph_name) if shape_keys else None
            if key_block is not None:
                placeholder.shape_key_remove(key_block)
    return removed


def _shape_key_max_displacement_squared(key_blocks, key_block):
    basis = key_blocks[0]
    coordinate_count = len(basis.data) * 3
    basis_coordinates = array("f", [0.0]) * coordinate_count
    key_coordinates = array("f", [0.0]) * coordinate_count
    basis.data.foreach_get("co", basis_coordinates)
    key_block.data.foreach_get("co", key_coordinates)
    maximum = 0.0
    for index in range(0, coordinate_count, 3):
        dx = key_coordinates[index] - basis_coordinates[index]
        dy = key_coordinates[index + 1] - basis_coordinates[index + 1]
        dz = key_coordinates[index + 2] - basis_coordinates[index + 2]
        maximum = max(maximum, dx * dx + dy * dy + dz * dz)
    return maximum


def _clean_near_zero_vertex_morph_shape_keys(root, morph_names, threshold):
    FnModel, _Model = _mmd_api()
    morph_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.morph"
    )
    threshold_squared = float(threshold) * float(threshold)
    removed = 0
    for mesh_object in FnModel.iterate_mesh_objects(root):
        key_blocks = getattr(
            getattr(mesh_object.data, "shape_keys", None),
            "key_blocks",
            None,
        )
        if key_blocks is None or not key_blocks:
            continue
        for morph_name in morph_names:
            key_block = key_blocks.get(morph_name)
            if key_block is None:
                continue
            if (
                _shape_key_max_displacement_squared(key_blocks, key_block)
                <= threshold_squared
            ):
                morph_module.FnMorph.remove_shape_key(mesh_object, morph_name)
                removed += 1
    return removed


class SPX_OT_RefreshMorphEditor(Operator):
    bl_idname = "surface_proxy.refresh_morph_editor"
    bl_label = "刷新 Morph 编辑器"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            self.report({"ERROR"}, "找不到 MMD 模型 Root")
            return {"CANCELLED"}
        settings.morph_editor_root = root
        restored = _restore_missing_vertex_morphs(root)
        ensure_morph_states(root)
        rebound = _bound_placeholder(root) is not None
        if rebound:
            _ensure_lightweight_bind(root, force_rebind=True)
            ensure_morph_states(root)
            evaluate_morph_root(root)
        if restored and rebound:
            self.report(
                {"INFO"},
                f"已补充 {restored} 个顶点 Morph，并重建 Bone/UV Runtime",
            )
        elif restored:
            self.report({"INFO"}, f"已补充 {restored} 个顶点 Morph")
        elif rebound:
            self.report({"INFO"}, "已刷新 Morph 并重建 Bone/UV Runtime")
        return {"FINISHED"}


class SPX_OT_CopySelectedMorphsToClipboard(Operator):
    bl_idname = "surface_proxy.copy_selected_morphs_to_clipboard"
    bl_label = "复制勾选 Morph"
    bl_description = (
        "按 PMX Editor CSV 格式复制勾选的 Morph；Bone、Material、Group 可跨模型，"
        "旧式 DATA UV 可复制，Vertex 与顶点组型 UV 会跳过"
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            self.report({"ERROR"}, "找不到 MMD 模型 Root")
            return {"CANCELLED"}
        ensure_morph_states(root)
        selected = [state for state in root.spx_morph_states if state.selected]
        if not selected and 0 <= root.spx_morph_active_index < len(
            root.spx_morph_states
        ):
            selected = [root.spx_morph_states[root.spx_morph_active_index]]
        typed_morphs = []
        for state in selected:
            morph = _morph_by_uid(root, state.morph_type, state.uid)
            if morph is not None:
                typed_morphs.append((state.morph_type, morph))
        text, copied, skipped = serialize_pmx_editor_morphs(root, typed_morphs)
        if copied == 0:
            self.report(
                {"ERROR"},
                "没有可安全复制的 Morph；Vertex 与顶点组型 UV 不支持跨模型复制",
            )
            return {"CANCELLED"}
        context.window_manager.clipboard = text
        message = f"已复制 {copied} 个 Morph 到剪贴板"
        if skipped:
            message += f"；跳过 {len(skipped)} 个 Vertex/顶点组型 UV Morph"
        self.report({"WARNING"} if skipped else {"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_PasteMorphsFromClipboard(Operator):
    bl_idname = "surface_proxy.paste_morphs_from_clipboard"
    bl_label = "从剪贴板粘贴 Morph"
    bl_description = (
        "读取 PMX Editor Morph CSV，并按类型自动写入 Bone、Material、Group；"
        "Group 中不存在的引用仍会保留，Vertex 与 UV 会安全跳过"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            self.report({"ERROR"}, "找不到 MMD 模型 Root")
            return {"CANCELLED"}
        try:
            records = parse_pmx_editor_morph_csv(context.window_manager.clipboard)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        result = apply_pmx_editor_morphs(root, records)
        ensure_morph_states(root)
        if result["applied"]:
            morph_type, morph_name = result["applied"][-1]
            settings.morph_editor_type = morph_type
            morph = _morph_collection(root, morph_type).get(morph_name)
            if morph is not None:
                uid = str(morph.get(MORPH_UID_PROPERTY, ""))
                index = root.spx_morph_states.find(uid)
                if index >= 0:
                    root.spx_morph_active_index = index
            if _bound_placeholder(root) is not None:
                _ensure_lightweight_bind(root, force_rebind=True)
                ensure_morph_states(root)
                evaluate_morph_root(root)
        imported = result["created"] + result["updated"]
        message = (
            f"已粘贴 {imported} 个 Morph"
            f"（新增 {result['created']}，更新 {result['updated']}）"
        )
        if result["skipped"]:
            message += f"；安全跳过 {len(result['skipped'])} 个 Vertex/UV Morph"
        if result["unresolved"]:
            message += f"；{len(result['unresolved'])} 个骨骼/材质引用未匹配"
        level = {"WARNING"} if result["skipped"] or result["unresolved"] else {"INFO"}
        self.report(level, message)
        return {"FINISHED"}


class SPX_OT_AddMorph(Operator):
    bl_idname = "surface_proxy.add_morph"
    bl_label = "新增 Morph"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        states = root.spx_morph_states
        active_uid = (
            states[root.spx_morph_active_index].uid
            if 0 <= root.spx_morph_active_index < len(states)
            and states[root.spx_morph_active_index].morph_type
            == settings.morph_editor_type
            else ""
        )
        morphs = _morph_collection(root, settings.morph_editor_type)
        morph = morphs.add()
        base = "新建 Morph"
        name = base
        suffix = 1
        while morphs.find(name) not in {-1, len(morphs) - 1}:
            suffix += 1
            name = f"{base}.{suffix:03d}"
        morph.name = name
        morph.name_e = name
        if settings.morph_editor_type == "uv_morphs":
            morph.data_type = "VERTEX_GROUP"
        morph[MORPH_UID_PROPERTY] = uuid.uuid4().hex
        new_uid = morph[MORPH_UID_PROPERTY]
        ensure_morph_states(root)
        if active_uid:
            type_states = [
                state
                for state in states
                if state.morph_type == settings.morph_editor_type
            ]
            order = [state.uid for state in type_states if state.uid != new_uid]
            if active_uid in order:
                insert_at = order.index(active_uid) + 1
                order.insert(insert_at, new_uid)
                positions = [
                    index
                    for index, state in enumerate(states)
                    if state.morph_type == settings.morph_editor_type
                ]
                desired_all = [state.uid for state in states]
                for position, uid in zip(positions, order, strict=False):
                    desired_all[position] = uid
                _set_collection_order(states, desired_all)
        _sync_morph_order(root)
        root.spx_morph_active_index = states.find(new_uid)
        return {"FINISHED"}


class SPX_OT_RemoveSelectedMorphs(Operator):
    bl_idname = "surface_proxy.remove_selected_morphs"
    bl_label = "删除勾选 Morph"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        selected = {
            state.uid
            for state in root.spx_morph_states
            if state.morph_type == settings.morph_editor_type and state.selected
        }
        if not selected and 0 <= root.spx_morph_active_index < len(root.spx_morph_states):
            state = root.spx_morph_states[root.spx_morph_active_index]
            if state.morph_type == settings.morph_editor_type:
                selected.add(state.uid)
        morphs = _morph_collection(root, settings.morph_editor_type)
        removed_names = [
            morph.name
            for morph in morphs
            if str(morph.get(MORPH_UID_PROPERTY, "")) in selected
        ]
        runtime_needs_rebind = (
            bool(removed_names)
            and settings.morph_editor_type == "uv_morphs"
            and _bound_placeholder(root) is not None
            and bool(root.get(RUNTIME_BOUND_PROPERTY, False))
        )
        if settings.morph_editor_type == "vertex_morphs":
            _remove_vertex_morph_shape_keys(root, removed_names)
        elif settings.morph_editor_type == "uv_morphs":
            _remove_uv_morph_runtime_data(root, removed_names)
        removed = 0
        for index in reversed(range(len(morphs))):
            if str(morphs[index].get(MORPH_UID_PROPERTY, "")) in selected:
                morphs.remove(index)
                removed += 1
        ensure_morph_states(root)
        root.spx_morph_active_index = min(
            root.spx_morph_active_index,
            max(0, len(root.spx_morph_states) - 1),
        )
        _sync_morph_order(root)
        if runtime_needs_rebind:
            _ensure_lightweight_bind(root, force_rebind=True)
        self.report({"INFO"}, f"已删除 {removed} 个 Morph")
        return {"FINISHED"}


def _morph_has_details(root, morph_type, morph):
    if morph_type == "vertex_morphs":
        FnModel, _Model = _mmd_api()
        return any(
            getattr(mesh_object.data, "shape_keys", None) is not None
            and mesh_object.data.shape_keys.key_blocks.get(morph.name) is not None
            for mesh_object in FnModel.iterate_mesh_objects(root)
        )
    if morph_type == "uv_morphs" and morph.data_type == "VERTEX_GROUP":
        FnModel, _Model = _mmd_api()
        morph_module = importlib.import_module(
            "bl_ext.blender_org.mmd_tools.core.morph"
        )
        return any(
            any(
                morph_module.FnMorph.get_uv_morph_vertex_groups(
                    mesh_object,
                    morph.name,
                )
            )
            for mesh_object in FnModel.iterate_mesh_objects(root)
        )
    if morph_type == "group_morphs":
        return any(
            offset.name
            in getattr(root.mmd_root, offset.morph_type, ())
            for offset in morph.data
        )
    return bool(morph.data)


class SPX_OT_CleanSelectedEmptyMorphs(Operator):
    bl_idname = "surface_proxy.clean_selected_empty_morphs"
    bl_label = "清理空 Morph"
    bl_description = "移除当前 Tab 已勾选且没有有效详情内容的 Morph"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        selected = {
            state.uid
            for state in root.spx_morph_states
            if state.morph_type == settings.morph_editor_type and state.selected
        }
        if not selected:
            self.report({"WARNING"}, "请先勾选当前 Tab 中的 Morph")
            return {"CANCELLED"}

        morphs = _morph_collection(root, settings.morph_editor_type)
        cleaned_shape_keys = 0
        if settings.morph_editor_type == "vertex_morphs":
            selected_names = [
                morph.name
                for morph in morphs
                if str(morph.get(MORPH_UID_PROPERTY, "")) in selected
            ]
            cleaned_shape_keys = _clean_near_zero_vertex_morph_shape_keys(
                root,
                selected_names,
                settings.morph_editor_shapekey_cleanup_threshold,
            )
        removed = 0
        removed_vertex_names = []
        for index in reversed(range(len(morphs))):
            morph = morphs[index]
            if (
                str(morph.get(MORPH_UID_PROPERTY, "")) in selected
                and not _morph_has_details(root, settings.morph_editor_type, morph)
            ):
                if settings.morph_editor_type == "vertex_morphs":
                    removed_vertex_names.append(morph.name)
                morphs.remove(index)
                removed += 1
        if removed_vertex_names:
            _remove_vertex_morph_shape_keys(root, removed_vertex_names)
        if not removed and not cleaned_shape_keys:
            self.report({"INFO"}, "勾选项中没有可清理的空 Morph")
            return {"CANCELLED"}

        ensure_morph_states(root)
        root.spx_morph_active_index = min(
            root.spx_morph_active_index,
            max(0, len(root.spx_morph_states) - 1),
        )
        _sync_morph_order(root)
        message = f"已清理 {removed} 个空 Morph"
        if cleaned_shape_keys:
            message += f"、{cleaned_shape_keys} 个阈值内 ShapeKey"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SPX_OT_SelectMorphs(Operator):
    bl_idname = "surface_proxy.select_morphs"
    bl_label = "选择 Morph"
    bl_options = {"INTERNAL"}

    action: EnumProperty(
        items=(("ALL", "全选", ""), ("NONE", "清除", ""), ("INVERT", "反选", "")),
        default="ALL",
    )

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        for state in root.spx_morph_states:
            if state.morph_type != settings.morph_editor_type:
                continue
            if self.action == "ALL":
                state.selected = True
            elif self.action == "NONE":
                state.selected = False
            else:
                state.selected = not state.selected
        return {"FINISHED"}


class SPX_OT_SelectMorphInterval(Operator):
    bl_idname = "surface_proxy.select_morph_interval"
    bl_label = "区间选组"
    bl_description = "以当前可见列表中最前和最后一个已勾选 Morph 为端点，补选两者之间的全部项目"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        search = settings.morph_editor_search.casefold().strip()
        visible_states = []
        for state in root.spx_morph_states:
            if state.morph_type != settings.morph_editor_type:
                continue
            morph = _morph_by_uid(root, state.morph_type, state.uid)
            if search and (
                morph is None
                or search not in f"{morph.name} {morph.name_e}".casefold()
            ):
                continue
            visible_states.append(state)
        selected_indices = [
            index for index, state in enumerate(visible_states) if state.selected
        ]
        if len(selected_indices) < 2:
            self.report({"WARNING"}, "区间选组至少需要勾选两个可见 Morph")
            return {"CANCELLED"}
        first_index = selected_indices[0]
        last_index = selected_indices[-1]
        added = 0
        for state in visible_states[first_index : last_index + 1]:
            if not state.selected:
                state.selected = True
                added += 1
        self.report({"INFO"}, f"已补选区间内 {added} 个 Morph")
        return {"FINISHED"}


class SPX_OT_CopyMorphJapaneseNamesToEnglish(Operator):
    bl_idname = "surface_proxy.copy_morph_japanese_names_to_english"
    bl_label = "日文名同步到英文名"
    bl_description = "将当前页所有已勾选 Morph 的日文名覆盖写入英文名"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        selected_states = [
            state
            for state in root.spx_morph_states
            if state.morph_type == settings.morph_editor_type and state.selected
        ]
        if not selected_states:
            self.report({"WARNING"}, "请先勾选 Morph")
            return {"CANCELLED"}

        changed = 0
        for state in selected_states:
            morph = _morph_by_uid(root, state.morph_type, state.uid)
            if morph is None:
                continue
            morph.name_e = morph.name
            changed += 1
        if not changed:
            return {"CANCELLED"}
        self.report({"INFO"}, f"已将 {changed} 个 Morph 的日文名同步到英文名")
        return {"FINISHED"}


def _translation_content(response_payload):
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("API 返回中缺少 choices[0].message.content") from exc
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict)
        )
    if not isinstance(content, str):
        raise ValueError("API 返回的翻译内容不是文本")
    return content.strip()


def _parse_morph_name_translations(content, expected_count):
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines.pop(0)
        if lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("模型没有返回 JSON 字符串数组")
    try:
        translations = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("模型返回的 JSON 无法解析") from exc
    if not isinstance(translations, list) or len(translations) != expected_count:
        raise ValueError(f"模型返回数量不匹配，应为 {expected_count} 项")
    if not all(isinstance(item, str) for item in translations):
        raise ValueError("模型返回数组中包含非字符串项目")
    return translations


def _morph_name_protected_markers(name):
    return "".join(
        character
        for character in name
        if unicodedata.category(character)[0] in {"N", "P", "S"}
    )


def _compact_english_morph_name(name):
    capitalized = re.sub(
        r"[A-Za-z]+",
        lambda match: match.group(0)[0].upper() + match.group(0)[1:],
        name,
    )
    return re.sub(r"\s+", "", capitalized)


def _normalize_morph_direction_tokens(name):
    found_tokens = []

    def remove_abbreviated(match):
        found_tokens.append(match.group(1))
        return ""

    def remove_full_word(match):
        found_tokens.append(
            {"Up": "Up", "Down": "Down", "Left": "L", "Right": "R"}[
                match.group(1)
            ]
        )
        return ""

    base_name = re.sub(r"_(Up|Down|L|R)(?=_|$)", remove_abbreviated, name)
    base_name = re.sub(
        r"(Up|Down|Left|Right)(?=[A-Z0-9_\W]|$)",
        remove_full_word,
        base_name,
    )
    base_name = re.sub(r"__+", "_", base_name).strip("_")
    ordered_tokens = [
        token
        for token in ("Up", "Down", "L", "R")
        if token in found_tokens
    ]
    return base_name + "".join(f"_{token}" for token in ordered_tokens)


def _protected_markers_preserved(source_name, translation):
    source_markers = _morph_name_protected_markers(source_name)
    translated_markers = iter(_morph_name_protected_markers(translation))
    return all(
        any(candidate == marker for candidate in translated_markers)
        for marker in source_markers
    )


def _validate_morph_name_translations(
    source_names,
    translations,
    max_characters=16,
):
    for index, (source_name, translation) in enumerate(
        zip(source_names, translations, strict=True),
        start=1,
    ):
        if len(translation) > max_characters:
            raise ValueError(
                f"第 {index} 项翻译超过 {max_characters} 个字符：{translation}"
            )
        if not _protected_markers_preserved(source_name, translation):
            raise ValueError(f"第 {index} 项翻译没有完整保留原名称符号：{translation}")
    return translations


def _request_morph_name_translations(
    preferences,
    source_names,
    max_characters=16,
    extra_instruction="",
):
    endpoint = _morph_ai_chat_completions_url(preferences.morph_ai_api_url)
    if not endpoint:
        raise ValueError("请先设置 API 请求地址")
    if not preferences.morph_ai_api_key.strip():
        raise ValueError("请先设置 API Key")
    if not preferences.morph_ai_model.strip():
        raise ValueError("请先设置调用模型")

    request_payload = {
        "model": preferences.morph_ai_model.strip(),
        "messages": (
            {
                "role": "system",
                "content": (
                    "Translate MMD morph names from Japanese or Chinese into concise English names. "
                    f"Keep each translated name as short as possible and never exceed {max_characters} characters "
                    "in total, counting symbols. Use compact PascalCase-style names with no spaces, "
                    "and capitalize the first letter of every English word. "
                    "Never spell out Left or Right: use suffix _L or _R. "
                    "If a direction is a prefix in the source name, move it to the corresponding suffix. "
                    "Encode vertical direction as suffix _Up or _Down. When both vertical and side "
                    "directions exist, put _Up or _Down before _L or _R, for example Pupil_Up_R. "
                    "Preserve every symbol, number, underscore, bracket, plus sign, "
                    "minus sign, and other non-language marker in its original position. "
                    "Return only a JSON array of strings in exactly the same order and length as the input. "
                    + extra_instruction
                ),
            },
            {
                "role": "user",
                "content": json.dumps(source_names, ensure_ascii=False),
            },
        ),
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {preferences.morph_ai_api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"API 请求失败（HTTP {exc.code}）：{detail[:400]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 API：{exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("API 返回的响应不是有效 UTF-8 JSON") from exc
    parsed_translations = _parse_morph_name_translations(
        _translation_content(response_payload),
        len(source_names),
    )
    compact_translations = [
        _normalize_morph_direction_tokens(
            _compact_english_morph_name(translation)
        )
        for translation in parsed_translations
    ]
    return _validate_morph_name_translations(
        source_names,
        compact_translations,
        max_characters=max_characters,
    )


class SPX_OT_TranslateMorphNamesWithAI(Operator):
    bl_idname = "surface_proxy.translate_morph_names_with_ai"
    bl_label = "AI翻译"
    bl_description = "将当前页已勾选 Morph 的日文或中文名称翻译为英文名"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        targets = []
        for state in root.spx_morph_states:
            if state.morph_type != settings.morph_editor_type or not state.selected:
                continue
            morph = _morph_by_uid(root, state.morph_type, state.uid)
            if morph is not None:
                targets.append(morph)
        if not targets:
            self.report({"WARNING"}, "请先勾选 Morph")
            return {"CANCELLED"}

        preferences = _addon_preferences(context)
        if preferences is None:
            self.report({"ERROR"}, "无法读取插件全局 AI 设置")
            return {"CANCELLED"}
        try:
            translations = _request_morph_name_translations(
                preferences,
                [morph.name for morph in targets],
            )
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for morph, translation in zip(targets, translations, strict=True):
            morph.name_e = translation
        self.report({"INFO"}, f"已翻译并填写 {len(targets)} 个 Morph 英文名")
        return {"FINISHED"}


class SPX_OT_MorphAISettings(Operator):
    bl_idname = "surface_proxy.morph_ai_settings"
    bl_label = "Morph AI 翻译设置"

    api_url: StringProperty(name="API 基础地址")
    api_key: StringProperty(name="API Key", subtype="PASSWORD")
    model: StringProperty(name="调用模型")

    def invoke(self, context, _event):
        preferences = _addon_preferences(context)
        if preferences is None:
            self.report({"ERROR"}, "无法读取插件全局 AI 设置")
            return {"CANCELLED"}
        self.api_url = _morph_ai_base_url(preferences.morph_ai_api_url)
        self.api_key = preferences.morph_ai_api_key
        self.model = preferences.morph_ai_model
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, _context):
        _draw_morph_ai_settings(self.layout, self)

    def execute(self, context):
        preferences = _addon_preferences(context)
        if preferences is None:
            return {"CANCELLED"}
        preferences.morph_ai_api_url = _morph_ai_base_url(self.api_url)
        preferences.morph_ai_api_key = self.api_key.strip()
        preferences.morph_ai_model = self.model.strip()
        try:
            bpy.ops.wm.save_userpref()
        except RuntimeError:
            self.report({"WARNING"}, "设置已写入；Blender 退出时将保存用户首选项")
            return {"FINISHED"}
        self.report({"INFO"}, "Morph AI 设置已全局保存")
        return {"FINISHED"}


class SPX_OT_ReorderMorphs(Operator):
    bl_idname = "surface_proxy.reorder_morphs"
    bl_label = "排序 Morph"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TOP", "置顶", ""),
            ("UP", "上移", ""),
            ("DOWN", "下移", ""),
            ("BOTTOM", "置底", ""),
            ("BEFORE", "插入活动项前", ""),
            ("AFTER", "插入活动项后", ""),
        )
    )

    @classmethod
    def description(cls, _context, properties):
        return {
            "TOP": "将勾选 Morph 置顶；未勾选时移动蓝色活动项",
            "UP": "将勾选 Morph 上移一位；未勾选时移动蓝色活动项",
            "DOWN": "将勾选 Morph 下移一位；未勾选时移动蓝色活动项",
            "BOTTOM": "将勾选 Morph 置底；未勾选时移动蓝色活动项",
            "BEFORE": "将勾选 Morph 作为一个块插入蓝色活动行之前",
            "AFTER": "将勾选 Morph 作为一个块插入蓝色活动行之后",
        }.get(properties.action, cls.bl_label)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None:
            return {"CANCELLED"}
        states = root.spx_morph_states
        type_states = [
            state for state in states if state.morph_type == settings.morph_editor_type
        ]
        active_uid = (
            states[root.spx_morph_active_index].uid
            if 0 <= root.spx_morph_active_index < len(states)
            and states[root.spx_morph_active_index].morph_type
            == settings.morph_editor_type
            else ""
        )
        selected = {state.uid for state in type_states if state.selected}
        if not selected:
            if self.action in {"TOP", "UP", "DOWN", "BOTTOM"} and active_uid:
                selected.add(active_uid)
            else:
                self.report({"WARNING"}, "请先勾选 Morph")
                return {"CANCELLED"}
        order = [state.uid for state in type_states]
        if self.action == "TOP":
            order = [uid for uid in order if uid in selected] + [
                uid for uid in order if uid not in selected
            ]
        elif self.action == "BOTTOM":
            order = [uid for uid in order if uid not in selected] + [
                uid for uid in order if uid in selected
            ]
        elif self.action == "UP":
            for index in range(1, len(order)):
                if order[index] in selected and order[index - 1] not in selected:
                    order[index - 1], order[index] = order[index], order[index - 1]
        elif self.action == "DOWN":
            for index in range(len(order) - 2, -1, -1):
                if order[index] in selected and order[index + 1] not in selected:
                    order[index], order[index + 1] = order[index + 1], order[index]
        elif self.action in {"BEFORE", "AFTER"}:
            if not active_uid:
                self.report({"WARNING"}, "请选择当前分类中的活动行作为插入位置")
                return {"CANCELLED"}
            if active_uid in selected:
                self.report({"WARNING"}, "活动行不能同时属于勾选块")
                return {"CANCELLED"}
            block = [uid for uid in order if uid in selected]
            remaining = [uid for uid in order if uid not in selected]
            insert_at = remaining.index(active_uid)
            if self.action == "AFTER":
                insert_at += 1
            order = remaining[:insert_at] + block + remaining[insert_at:]
        else:
            self.report({"ERROR"}, f"未知排序动作：{self.action}")
            return {"CANCELLED"}

        positions = [
            index
            for index, state in enumerate(states)
            if state.morph_type == settings.morph_editor_type
        ]
        desired_all = [state.uid for state in states]
        for position, uid in zip(positions, order, strict=False):
            desired_all[position] = uid
        _set_collection_order(states, desired_all)
        _sync_morph_order(root)
        if active_uid:
            root.spx_morph_active_index = states.find(active_uid)
        return {"FINISHED"}


def _bone_morph_weighted_vertices(root, bone_morph):
    FnModel, _Model = _mmd_api()
    armature = FnModel.find_armature_object(root)
    source_bone_names = {offset.bone for offset in bone_morph.data if offset.bone}
    if armature is None or not source_bone_names:
        return {}

    bone_names = set()
    pending_bones = [
        armature.pose.bones.get(name)
        for name in source_bone_names
        if armature.pose.bones.get(name) is not None
    ]
    while pending_bones:
        pose_bone = pending_bones.pop()
        if pose_bone.name in bone_names:
            continue
        bone_names.add(pose_bone.name)
        pending_bones.extend(pose_bone.children)

    result = {}
    for mesh_object in FnModel.iterate_mesh_objects(root):
        if not any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in mesh_object.modifiers
        ):
            continue
        group_indices = {
            group.index
            for bone_name in bone_names
            if (group := mesh_object.vertex_groups.get(bone_name)) is not None
        }
        if not group_indices:
            continue
        vertex_indices = {
            vertex.index
            for vertex in mesh_object.data.vertices
            if any(
                assignment.group in group_indices and assignment.weight > 0.0
                for assignment in vertex.groups
            )
        }
        if vertex_indices:
            result[mesh_object] = vertex_indices
    return result


def _limit_shape_key_to_vertices(mesh_object, shape_key_name, vertex_indices):
    shape_keys = mesh_object.data.shape_keys
    if shape_keys is None:
        return
    shape_key = shape_keys.key_blocks.get(shape_key_name)
    if shape_key is None or shape_key.relative_key is None:
        return
    point_count = len(shape_key.data)
    basis_coordinates = array("f", [0.0]) * (point_count * 3)
    shape_coordinates = array("f", [0.0]) * (point_count * 3)
    shape_key.relative_key.data.foreach_get("co", basis_coordinates)
    shape_key.data.foreach_get("co", shape_coordinates)
    for vertex_index in vertex_indices:
        coordinate_index = vertex_index * 3
        basis_coordinates[coordinate_index : coordinate_index + 3] = (
            shape_coordinates[coordinate_index : coordinate_index + 3]
        )
    shape_key.data.foreach_set("co", basis_coordinates)


def _run_filtered_bone_morph_conversion(context, root, bone_morph):
    FnModel, _Model = _mmd_api()
    weighted_vertices = _bone_morph_weighted_vertices(root, bone_morph)
    if not weighted_vertices:
        return {"CANCELLED"}, 0, len(tuple(FnModel.iterate_mesh_objects(root)))

    target_meshes = list(weighted_vertices)
    all_mesh_count = len(tuple(FnModel.iterate_mesh_objects(root)))
    original_name = bone_morph.name
    target_name = original_name[:-1] if original_name.endswith("B") else original_name
    original_iterator = FnModel.__dict__["iterate_mesh_objects"]
    original_function = original_iterator.__func__
    target_root_pointer = root.as_pointer()

    def filtered_iterator(candidate_root):
        if (
            candidate_root is not None
            and candidate_root.as_pointer() == target_root_pointer
        ):
            return iter(target_meshes)
        return original_function(candidate_root)

    previous_active = context.view_layer.objects.active
    try:
        context.view_layer.objects.active = root
        FnModel.iterate_mesh_objects = staticmethod(filtered_iterator)
        result = bpy.ops.mmd_tools.convert_bone_morph_to_vertex_morph()
        if result == {"FINISHED"}:
            for mesh_object, vertex_indices in weighted_vertices.items():
                _limit_shape_key_to_vertices(
                    mesh_object,
                    target_name,
                    vertex_indices,
                )
    finally:
        FnModel.iterate_mesh_objects = original_iterator
        if previous_active is not None and previous_active.name in context.view_layer.objects:
            context.view_layer.objects.active = previous_active
    return result, len(target_meshes), all_mesh_count


class SPX_OT_ConvertWeightedBoneMorphToVertexMorph(Operator):
    bl_idname = "surface_proxy.convert_weighted_bone_morph"
    bl_label = "转换为 Vertex Morph"
    bl_description = "只在当前 Bone Morph 所引用骨骼及其全部子孙骨骼具有非零顶点权重的网格上创建或更新 ShapeKey"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        if root is None or root.mmd_root.active_morph_type != "bone_morphs":
            return False
        index = root.mmd_root.active_morph
        return 0 <= index < len(root.mmd_root.bone_morphs)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        index = root.mmd_root.active_morph
        bone_morph = root.mmd_root.bone_morphs[index]
        result, target_count, all_mesh_count = _run_filtered_bone_morph_conversion(
            context,
            root,
            bone_morph,
        )
        if result != {"FINISHED"}:
            self.report(
                {"WARNING"},
                "该 Bone Morph 引用的骨骼及其子孙骨骼在模型网格中没有非零顶点权重",
            )
            return result
        ensure_morph_states(root)
        self.report(
            {"INFO"},
            f"已在 {target_count} 个具权重网格上转换；跳过 {all_mesh_count - target_count} 个无关网格",
        )
        return {"FINISHED"}


class SPX_OT_BatchConvertWeightedBoneMorphsToVertexMorphs(Operator):
    bl_idname = "surface_proxy.batch_convert_weighted_bone_morphs"
    bl_label = "批量转换为 Vertex Morph"
    bl_description = "批量转换全部 Bone Morph，每个 Morph 只处理其骨骼及全部子孙骨骼具有非零顶点权重的网格"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        return root is not None and bool(root.mmd_root.bone_morphs)

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        converted = 0
        skipped = 0
        for index in range(len(root.mmd_root.bone_morphs)):
            root.mmd_root.active_morph_type = "bone_morphs"
            root.mmd_root.active_morph = index
            bone_morph = root.mmd_root.bone_morphs[index]
            if not bone_morph.data:
                skipped += 1
                continue
            result, _target_count, _all_mesh_count = (
                _run_filtered_bone_morph_conversion(context, root, bone_morph)
            )
            if result == {"FINISHED"}:
                converted += 1
            else:
                skipped += 1
        ensure_morph_states(root)
        self.report(
            {"INFO"},
            f"已转换 {converted} 个 Bone Morph；跳过 {skipped} 个无权重或空 Morph",
        )
        return {"FINISHED"}


class SPX_OT_AddMorphOffset(Operator):
    bl_idname = "surface_proxy.add_morph_offset"
    bl_label = "新增 Morph Offset"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def description(cls, context, _properties):
        settings = getattr(context.scene, "surface_proxy_creator", None)
        root = _find_root(context, settings) if settings is not None else None
        if root is not None and root.mmd_root.active_morph_type == "material_morphs":
            return "将当前 MMD 模型内已选 Mesh 的材质按真实 PMX 顺序插入活动详情项下方"
        return "新增一个空 Morph 详情项"

    def _add_selected_materials(self, context, root, morph):
        FnModel, _Model = _mmd_api()
        selected_meshes = {
            obj
            for obj in context.selected_objects
            if obj.type == "MESH" and FnModel.find_root_object(obj) == root
        }
        if not selected_meshes:
            self.report({"WARNING"}, "请先选择当前 MMD 模型中的 Mesh")
            return {"CANCELLED"}

        material_owners = {}
        for mesh_object in FnModel.iterate_mesh_objects(root):
            if mesh_object not in selected_meshes:
                continue
            for material_slot in mesh_object.material_slots:
                material = material_slot.material
                if material is not None and material not in material_owners:
                    material_owners[material] = mesh_object.data.name

        existing_materials = {data.material for data in morph.data if data.material}
        candidates = []
        for material in ordered_materials(root, FnModel):
            mesh_name = material_owners.get(material)
            if mesh_name is None or material.name in existing_materials:
                continue
            existing_materials.add(material.name)
            candidates.append((mesh_name, material.name))
        for material, mesh_name in material_owners.items():
            if material.name in existing_materials:
                continue
            existing_materials.add(material.name)
            candidates.append((mesh_name, material.name))
        if not candidates:
            self.report({"WARNING"}, "所选 Mesh 的材质已全部存在于当前 Morph")
            return {"CANCELLED"}

        insert_at = (
            min(max(morph.active_data, 0), len(morph.data) - 1) + 1
            if morph.data
            else 0
        )
        first_inserted = insert_at
        for mesh_name, material_name in candidates:
            data = morph.data.add()
            data.related_mesh = mesh_name
            data.material = material_name
            source_index = len(morph.data) - 1
            if source_index != insert_at:
                morph.data.move(source_index, insert_at)
            insert_at += 1
        morph.active_data = first_inserted
        evaluate_morph_root(root)
        self.report({"INFO"}, f"已添加 {len(candidates)} 个材质详情项")
        return {"FINISHED"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        morph = _active_morph(root)
        if morph is None or not hasattr(morph, "data"):
            return {"CANCELLED"}
        if root.mmd_root.active_morph_type == "material_morphs":
            return self._add_selected_materials(context, root, morph)
        morph.data.add()
        morph.active_data = len(morph.data) - 1
        evaluate_morph_root(root)
        return {"FINISHED"}


class SPX_OT_RemoveMorphOffset(Operator):
    bl_idname = "surface_proxy.remove_morph_offset"
    bl_label = "删除 Morph Offset"
    bl_description = "删除勾选详情项；未勾选时删除蓝色活动项"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        morph = _active_morph(root)
        if morph is None or not getattr(morph, "data", None):
            return {"CANCELLED"}
        remove_indices = [
            index
            for index, data in enumerate(morph.data)
            if bool(getattr(data, DETAIL_SELECTED_PROPERTY, False))
        ]
        if not remove_indices:
            remove_indices = [min(max(morph.active_data, 0), len(morph.data) - 1)]
        next_active_index = remove_indices[0]
        for index in reversed(remove_indices):
            morph.data.remove(index)
        morph.active_data = min(next_active_index, max(0, len(morph.data) - 1))
        evaluate_morph_root(root)
        self.report({"INFO"}, f"已删除 {len(remove_indices)} 个 Morph 详情项")
        return {"FINISHED"}


class SPX_OT_ReorderMorphOffsets(Operator):
    bl_idname = "surface_proxy.reorder_morph_offsets"
    bl_label = "排序 Morph 详情项"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("TOP", "置顶", ""),
            ("UP", "上移", ""),
            ("DOWN", "下移", ""),
            ("BOTTOM", "置底", ""),
            ("BEFORE", "插入活动项前", ""),
            ("AFTER", "插入活动项后", ""),
        ),
        options={"HIDDEN"},
    )

    @classmethod
    def description(cls, _context, properties):
        return {
            "TOP": "将勾选详情项置顶；未勾选时移动蓝色活动项",
            "UP": "将勾选详情项上移一位；未勾选时移动蓝色活动项",
            "DOWN": "将勾选详情项下移一位；未勾选时移动蓝色活动项",
            "BOTTOM": "将勾选详情项置底；未勾选时移动蓝色活动项",
            "BEFORE": "将勾选详情项作为一个块插入蓝色活动行之前",
            "AFTER": "将勾选详情项作为一个块插入蓝色活动行之后",
        }.get(properties.action, cls.bl_label)

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        morph = _active_morph(root)
        if morph is None or not getattr(morph, "data", None):
            return {"CANCELLED"}
        selected_indices = {
            index
            for index, data in enumerate(morph.data)
            if bool(getattr(data, DETAIL_SELECTED_PROPERTY, False))
        }
        active_index = min(max(morph.active_data, 0), len(morph.data) - 1)
        if not selected_indices:
            if self.action in {"TOP", "UP", "DOWN", "BOTTOM"}:
                selected_indices.add(active_index)
            else:
                self.report({"WARNING"}, "请先勾选 Morph 详情项")
                return {"CANCELLED"}

        order = list(range(len(morph.data)))
        if self.action == "TOP":
            order = [i for i in order if i in selected_indices] + [
                i for i in order if i not in selected_indices
            ]
        elif self.action == "BOTTOM":
            order = [i for i in order if i not in selected_indices] + [
                i for i in order if i in selected_indices
            ]
        elif self.action == "UP":
            for index in range(1, len(order)):
                if (
                    order[index] in selected_indices
                    and order[index - 1] not in selected_indices
                ):
                    order[index - 1], order[index] = order[index], order[index - 1]
        elif self.action == "DOWN":
            for index in range(len(order) - 2, -1, -1):
                if (
                    order[index] in selected_indices
                    and order[index + 1] not in selected_indices
                ):
                    order[index], order[index + 1] = order[index + 1], order[index]
        elif self.action in {"BEFORE", "AFTER"}:
            if active_index in selected_indices:
                self.report({"WARNING"}, "活动行不能同时属于勾选块")
                return {"CANCELLED"}
            block = [i for i in order if i in selected_indices]
            remaining = [i for i in order if i not in selected_indices]
            insert_at = remaining.index(active_index)
            if self.action == "AFTER":
                insert_at += 1
            order = remaining[:insert_at] + block + remaining[insert_at:]
        else:
            self.report({"ERROR"}, f"未知排序动作：{self.action}")
            return {"CANCELLED"}

        token_property = "_spx_reorder_token"
        marker = uuid.uuid4().hex
        try:
            tokens = []
            for index, data in enumerate(morph.data):
                token = f"{marker}:{index}"
                data[token_property] = token
                tokens.append(token)
            desired_tokens = [tokens[index] for index in order]
            active_token = tokens[active_index]
            for target_index, token in enumerate(desired_tokens):
                current_index = next(
                    index
                    for index, data in enumerate(morph.data)
                    if data.get(token_property) == token
                )
                if current_index != target_index:
                    morph.data.move(current_index, target_index)
            morph.active_data = next(
                index
                for index, data in enumerate(morph.data)
                if data.get(token_property) == active_token
            )
        finally:
            for data in morph.data:
                if token_property in data:
                    del data[token_property]
        evaluate_morph_root(root)
        return {"FINISHED"}


class SPX_OT_ApplyMaterialMorphPreset(Operator):
    bl_idname = "surface_proxy.apply_material_morph_preset"
    bl_label = "应用 Material Morph 预设"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(
        items=(
            ("HIDE", "隐藏", "将目标详情行设为相加隐藏参数"),
            ("SHOW", "显示", "将目标详情行设为相加显示参数"),
        ),
        options={"HIDDEN"},
    )

    @classmethod
    def description(cls, _context, properties):
        if properties.preset == "HIDE":
            return "单个目标直接应用；多个目标将勾选详情行设为相加，漫射与边缘 Alpha 为 -1，其余参数为 0"
        return "单个目标直接应用；多个目标将勾选详情行设为相加，漫射与边缘 Alpha 为 1，其余参数为 0"

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        morph = _active_morph(root)
        if morph is None or root.mmd_root.active_morph_type != "material_morphs":
            return {"CANCELLED"}
        selected = [
            data
            for data in morph.data
            if bool(getattr(data, DETAIL_SELECTED_PROPERTY, False))
        ]
        if not selected and len(morph.data) == 1:
            selected = [morph.data[0]]
        if not selected:
            self.report({"WARNING"}, "请先勾选 Material Morph 详情行")
            return {"CANCELLED"}

        alpha = -1.0 if self.preset == "HIDE" else 1.0
        for data in selected:
            data.offset_type = "ADD"
            data.diffuse_color = (0.0, 0.0, 0.0, alpha)
            data.specular_color = (0.0, 0.0, 0.0)
            data.shininess = 0.0
            data.ambient_color = (0.0, 0.0, 0.0)
            data.edge_color = (0.0, 0.0, 0.0, alpha)
            data.edge_weight = 0.0
            data.texture_factor = (0.0, 0.0, 0.0, 0.0)
            data.sphere_texture_factor = (0.0, 0.0, 0.0, 0.0)
            data.toon_texture_factor = (0.0, 0.0, 0.0, 0.0)
        evaluate_morph_root(root)
        preset_name = "隐藏" if self.preset == "HIDE" else "显示"
        self.report({"INFO"}, f"已向 {len(selected)} 个详情行应用“{preset_name}”预设")
        return {"FINISHED"}


class SPX_OT_SelectMorphDetails(Operator):
    bl_idname = "surface_proxy.select_morph_details"
    bl_label = "选择 Morph 详情行"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(
            ("ALL", "全选", ""),
            ("NONE", "全不选", ""),
            ("INVERT", "反选", ""),
            ("INTERVAL", "区间选组", ""),
        ),
        options={"HIDDEN"},
    )

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        morph = _active_morph(root)
        if morph is None:
            return {"CANCELLED"}
        if root.mmd_root.active_morph_type == "vertex_morphs":
            FnModel, _Model = _mmd_api()
            targets = [
                mesh_object
                for mesh_object in FnModel.iterate_mesh_objects(root)
                if getattr(mesh_object.data, "shape_keys", None) is not None
                and mesh_object.data.shape_keys.key_blocks.get(morph.name) is not None
            ]
            property_name = VERTEX_DETAIL_SELECTED_PROPERTY
        else:
            targets = list(getattr(morph, "data", ()))
            property_name = DETAIL_SELECTED_PROPERTY
        if not targets:
            return {"CANCELLED"}
        if self.action == "INTERVAL":
            selected_indices = [
                index
                for index, target in enumerate(targets)
                if getattr(target, property_name)
            ]
            if len(selected_indices) < 2:
                self.report({"WARNING"}, "区间选组至少需要勾选两个详情行")
                return {"CANCELLED"}
            added = 0
            for target in targets[selected_indices[0] : selected_indices[-1] + 1]:
                if not getattr(target, property_name):
                    setattr(target, property_name, True)
                    added += 1
            self.report({"INFO"}, f"已补选区间内 {added} 个详情行")
            return {"FINISHED"}
        for target in targets:
            if self.action == "ALL":
                setattr(target, property_name, True)
            elif self.action == "NONE":
                setattr(target, property_name, False)
            else:
                setattr(target, property_name, not getattr(target, property_name))
        return {"FINISHED"}


class SPX_OT_CollectSelectedMorphsIntoGroup(Operator):
    bl_idname = "surface_proxy.collect_selected_morphs_into_group"
    bl_label = "将其它 Tab 勾选 Morph 加入当前组"
    bl_description = "将材质、UV、骨骼和顶点 Tab 中已勾选的 Morph 加入当前 Group Morph，默认权重为 1"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None or not (
            0 <= root.spx_morph_active_index < len(root.spx_morph_states)
        ):
            return {"CANCELLED"}
        active_state = root.spx_morph_states[root.spx_morph_active_index]
        if active_state.morph_type != "group_morphs":
            return {"CANCELLED"}
        group_morph = _morph_by_uid(root, active_state.morph_type, active_state.uid)
        if group_morph is None:
            return {"CANCELLED"}

        selected = []
        for state in root.spx_morph_states:
            if state.morph_type == "group_morphs" or not state.selected:
                continue
            morph = _morph_by_uid(root, state.morph_type, state.uid)
            if morph is not None:
                selected.append((state.morph_type, morph.name))
        if not selected:
            self.report({"WARNING"}, "请先在材质、UV、骨骼或顶点 Tab 勾选 Morph")
            return {"CANCELLED"}

        existing = {(data.morph_type, data.name) for data in group_morph.data}
        candidates = [item for item in selected if item not in existing]
        if not candidates:
            self.report({"WARNING"}, "勾选的 Morph 已全部存在于当前 Group Morph")
            return {"CANCELLED"}

        insert_at = (
            min(max(group_morph.active_data, 0), len(group_morph.data) - 1) + 1
            if group_morph.data
            else 0
        )
        first_inserted = insert_at
        for morph_type, morph_name in candidates:
            data = group_morph.data.add()
            data.morph_type = morph_type
            data.name = morph_name
            data.factor = 1.0
            source_index = len(group_morph.data) - 1
            if source_index != insert_at:
                group_morph.data.move(source_index, insert_at)
            insert_at += 1
        group_morph.active_data = first_inserted
        evaluate_morph_root(root)
        duplicate_count = len(selected) - len(candidates)
        message = f"已将 {len(candidates)} 个 Morph 加入当前 Group Morph"
        if duplicate_count:
            message += f"；跳过 {duplicate_count} 个重复项"
        self.report({"INFO"}, message)
        return {"FINISHED"}


def _active_morph(root):
    if root is None or not (0 <= root.spx_morph_active_index < len(root.spx_morph_states)):
        return None
    state = root.spx_morph_states[root.spx_morph_active_index]
    return _morph_by_uid(root, state.morph_type, state.uid)


def _clear_uv_morph_preview(root):
    FnModel, _Model = _mmd_api()
    for mesh_object in FnModel.iterate_mesh_objects(root):
        mesh = mesh_object.data
        uv_layers = mesh.uv_layers
        temp_names = tuple(
            layer.name for layer in uv_layers if layer.name.startswith("__uv.")
        )
        if temp_names:
            active_name = uv_layers.active.name if uv_layers.active is not None else ""
            preferred_name = active_name[5:] if active_name.startswith("__uv.") else ""
            stable_layer = uv_layers.get(preferred_name)
            if stable_layer is None:
                stable_layer = next(
                    (layer for layer in uv_layers if not layer.name.startswith("__uv.")),
                    None,
                )
            if stable_layer is not None:
                uv_layers.active = stable_layer
                stable_layer.active_render = True
                mesh.update()
            for name in temp_names:
                layer = uv_layers.get(name)
                if layer is not None:
                    uv_layers.remove(layer)
            mesh.update()

        animation_data = mesh.animation_data
        if animation_data is not None:
            for track in tuple(animation_data.nla_tracks):
                if track.name.startswith("__uv."):
                    animation_data.nla_tracks.remove(track)
            if (
                animation_data.action is not None
                and animation_data.action.name.startswith("__uv.")
            ):
                animation_data.action = None
            if animation_data.action is None and not animation_data.nla_tracks:
                mesh.animation_data_clear()

    for action in tuple(bpy.data.actions):
        if action.name.startswith("__uv.") and action.users < 1:
            bpy.data.actions.remove(action)


def _create_uv_morph_preview(root, mesh_object, morph):
    morph_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.morph"
    )
    mesh = mesh_object.data
    uv_layers = mesh.uv_layers
    base_uv_layers = [layer for layer in uv_layers if not layer.name.startswith("_")]
    if morph.uv_index >= len(base_uv_layers):
        raise ValueError(f"无效 UV 层索引: {morph.uv_index}")

    base_layer = base_uv_layers[morph.uv_index]
    active_layer = uv_layers.active
    valid_names = {base_layer.name, "_" + base_layer.name}
    if morph.uv_index == 0 or active_layer is None or active_layer.name not in valid_names:
        active_layer = base_layer
        uv_layers.active = active_layer

    source_name = active_layer.name
    temp_layer = uv_layers.new(name=f"__uv.{source_name}", do_init=True)
    offsets = morph_module.FnMorph.get_uv_morph_offset_map(mesh_object, morph)
    component = "zw" if source_name.startswith("_") else "xy"
    offset_map = {
        vertex_index: getattr(Vector(offset), component)
        for vertex_index, offset in offsets.items()
    }
    if offset_map:
        source_data = uv_layers[source_name].data
        temp_data = temp_layer.data
        for index, loop in enumerate(mesh.loops):
            selected = loop.vertex_index in offset_map
            temp_data[index].select = selected
            if selected:
                temp_data[index].uv = source_data[index].uv + offset_map[loop.vertex_index]
    uv_layers.active = temp_layer
    temp_layer.active_render = True
    mesh.update()
    mesh_object.hide_set(False)


class SPX_OT_ViewUVMorph(Operator):
    bl_idname = "surface_proxy.view_uv_morph"
    bl_label = "查看 UV Morph"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        settings = context.scene.surface_proxy_creator
        root = _find_root(context, settings)
        morph = _active_morph(root)
        if root is None or morph is None:
            return {"CANCELLED"}
        FnModel, _Model = _mmd_api()
        meshes = tuple(FnModel.iterate_mesh_objects(root))
        mesh_object = context.active_object
        if len(meshes) == 1:
            mesh_object = meshes[0]
        elif mesh_object not in meshes:
            self.report({"ERROR"}, "请选择当前 MMD 模型中的网格")
            return {"CANCELLED"}
        root_name = root.name
        mesh_name = mesh_object.name
        morph_uid = str(morph.get(MORPH_UID_PROPERTY, ""))

        def update_preview():
            current_root = bpy.data.objects.get(root_name)
            current_mesh = bpy.data.objects.get(mesh_name)
            if current_root is None or current_mesh is None:
                return None
            current_morph = _morph_by_uid(current_root, "uv_morphs", morph_uid)
            if current_morph is None:
                return None
            try:
                _clear_uv_morph_preview(current_root)
                _create_uv_morph_preview(current_root, current_mesh, current_morph)
                if RUNTIME_ERROR_PROPERTY in current_root:
                    del current_root[RUNTIME_ERROR_PROPERTY]
            except Exception as error:
                current_root[RUNTIME_ERROR_PROPERTY] = str(error)
            _tag_view3d_redraw()
            return None

        bpy.app.timers.register(update_preview, first_interval=0.0)
        return {"FINISHED"}


class SPX_OT_ClearUVMorphPreview(Operator):
    bl_idname = "surface_proxy.clear_uv_morph_preview"
    bl_label = "清除 UV Morph 预览"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        root = _find_root(context, context.scene.surface_proxy_creator)
        if root is None:
            return {"CANCELLED"}
        root_name = root.name

        def clear_preview():
            current_root = bpy.data.objects.get(root_name)
            if current_root is not None:
                try:
                    _clear_uv_morph_preview(current_root)
                    if RUNTIME_ERROR_PROPERTY in current_root:
                        del current_root[RUNTIME_ERROR_PROPERTY]
                except Exception as error:
                    current_root[RUNTIME_ERROR_PROPERTY] = str(error)
            _tag_view3d_redraw()
            return None

        bpy.app.timers.register(clear_preview, first_interval=0.0)
        return {"FINISHED"}


class _SPX_UL_MorphOffsets(UIList):
    official_list = ""

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        row = layout.row(align=True)
        row.prop(item, DETAIL_SELECTED_PROPERTY, text="")
        official_class = getattr(bpy.types, self.official_list, None)
        if official_class is None:
            row.label(text=str(index))
            return
        official_class.draw_item(
            self,
            context,
            row,
            data,
            item,
            icon,
            active_data,
            active_propname,
            index,
        )


class SPX_UL_MaterialMorphOffsets(_SPX_UL_MorphOffsets):
    official_list = "MMD_TOOLS_UL_MaterialMorphOffsets"


class SPX_UL_UVMorphOffsets(_SPX_UL_MorphOffsets):
    official_list = "MMD_TOOLS_UL_UVMorphOffsets"


class SPX_UL_BoneMorphOffsets(_SPX_UL_MorphOffsets):
    official_list = "MMD_TOOLS_UL_BoneMorphOffsets"


class SPX_UL_GroupMorphOffsets(_SPX_UL_MorphOffsets):
    official_list = "MMD_TOOLS_UL_GroupMorphOffsets"

    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        icon,
        _active_data,
        _active_propname,
        _index,
    ):
        row = layout.row(align=True)
        row.prop(item, DETAIL_SELECTED_PROPERTY, text="")
        if self.layout_type == "DEFAULT":
            fields = row.split(factor=0.5, align=True)
            fields.prop(item, "name", text="", emboss=False, icon="SHAPEKEY_DATA")
            values = fields.row(align=True)
            values.prop(item, "morph_type", text="", emboss=False)
            if item.name in getattr(item.id_data.mmd_root, item.morph_type):
                values.prop(
                    item,
                    GROUP_FACTOR_PROXY_PROPERTY,
                    text="",
                    emboss=False,
                    slider=True,
                )
            else:
                values.label(icon="ERROR")
        elif self.layout_type == "GRID":
            row.alignment = "CENTER"
            row.label(text="", icon_value=icon)


class SPX_OT_SelectVertexMorphObject(Operator):
    bl_idname = "surface_proxy.select_vertex_morph_object"
    bl_label = "选择 Vertex Morph 物体"
    bl_description = "独选并高亮该网格，同时切换到当前 Vertex Morph 的 ShapeKey"
    bl_options = {"REGISTER", "UNDO"}

    root_name: StringProperty(options={"HIDDEN"})
    object_name: StringProperty(options={"HIDDEN"})
    morph_uid: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        root = bpy.data.objects.get(self.root_name)
        mesh_object = bpy.data.objects.get(self.object_name)
        if root is None or mesh_object is None:
            self.report({"ERROR"}, "Vertex Morph 目标已经失效")
            return {"CANCELLED"}
        morph = _morph_by_uid(root, "vertex_morphs", self.morph_uid)
        if morph is None:
            self.report({"ERROR"}, "Vertex Morph 目标已经失效")
            return {"CANCELLED"}
        FnModel, _Model = _mmd_api()
        if mesh_object not in set(FnModel.iterate_mesh_objects(root)):
            self.report({"ERROR"}, "目标网格不属于当前 MMD 模型")
            return {"CANCELLED"}
        if mesh_object.name not in context.view_layer.objects:
            self.report({"ERROR"}, "目标网格不在当前 View Layer")
            return {"CANCELLED"}
        active_object = context.view_layer.objects.active
        if active_object is not None and active_object.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                self.report({"ERROR"}, "请先退出当前编辑模式")
                return {"CANCELLED"}
        mesh_object.hide_set(False)
        for obj in context.view_layer.objects:
            if obj.select_get():
                obj.select_set(False)
        mesh_object.select_set(True)
        context.view_layer.objects.active = mesh_object
        shape_keys = getattr(mesh_object.data, "shape_keys", None)
        if shape_keys is not None:
            shape_key_index = shape_keys.key_blocks.find(morph.name)
            if shape_key_index >= 0:
                mesh_object.active_shape_key_index = shape_key_index
        return {"FINISHED"}


def _draw_offset_list(layout, morph, list_name):
    row = layout.row()
    row.template_list(list_name, "spx", morph, "data", morph, "active_data", rows=8)
    buttons = row.column(align=True)
    buttons.operator("surface_proxy.add_morph_offset", text="", icon="ADD")
    buttons.operator("surface_proxy.remove_morph_offset", text="", icon="REMOVE")
    buttons.separator(factor=0.5)
    for action, icon in (
        ("TOP", "TRIA_UP_BAR"),
        ("UP", "TRIA_UP"),
        ("DOWN", "TRIA_DOWN"),
        ("BOTTOM", "TRIA_DOWN_BAR"),
    ):
        operator = buttons.operator(
            SPX_OT_ReorderMorphOffsets.bl_idname,
            text="",
            icon=icon,
        )
        operator.action = action
    buttons.separator(factor=0.5)
    for action, icon in (("BEFORE", "ANCHOR_TOP"), ("AFTER", "ANCHOR_BOTTOM")):
        operator = buttons.operator(
            SPX_OT_ReorderMorphOffsets.bl_idname,
            text="",
            icon=icon,
        )
        operator.action = action
    _draw_detail_selection_buttons(layout)


def _draw_detail_selection_buttons(layout):
    selection = layout.row(align=True)
    selection.operator(
        SPX_OT_SelectMorphDetails.bl_idname,
        text="全选",
    ).action = "ALL"
    selection.operator(
        SPX_OT_SelectMorphDetails.bl_idname,
        text="全不选",
    ).action = "NONE"
    selection.operator(
        SPX_OT_SelectMorphDetails.bl_idname,
        text="反选",
    ).action = "INVERT"
    selection.operator(
        SPX_OT_SelectMorphDetails.bl_idname,
        text="区间选组",
    ).action = "INTERVAL"


def _draw_material_details(layout, morph):
    _draw_offset_list(layout, morph, "SPX_UL_MaterialMorphOffsets")
    if not morph.data:
        return
    data = morph.data[morph.active_data]
    material_column = layout.column(align=True)
    material_column.prop_search(data, "related_mesh", bpy.data, "meshes", text="相关网格")
    related_mesh = bpy.data.meshes.get(data.related_mesh)
    material_column.prop_search(
        data,
        "material",
        related_mesh or bpy.data,
        "materials",
        text="材质",
    )
    presets = layout.row(align=True)
    operator = presets.operator(
        SPX_OT_ApplyMaterialMorphPreset.bl_idname,
        text="预设：隐藏",
    )
    operator.preset = "HIDE"
    operator = presets.operator(
        SPX_OT_ApplyMaterialMorphPreset.bl_idname,
        text="预设：显示",
    )
    operator.preset = "SHOW"
    row = layout.row()
    row.prop(data, "offset_type", expand=True)
    initialize = row.row(align=True)
    initialize.operator(
        "mmd_tools.material_morph_offset_init",
        text="",
        icon="TRIA_LEFT",
    ).target_value = 0
    initialize.operator(
        "mmd_tools.material_morph_offset_init",
        text="",
        icon="TRIA_RIGHT",
    ).target_value = 1
    row = layout.row()
    row.column(align=True).prop(data, "diffuse_color", expand=True, slider=True)
    specular = row.column(align=True)
    specular.prop(data, "specular_color", expand=True, slider=True)
    specular.prop(data, "shininess", slider=True)
    row.column(align=True).prop(data, "ambient_color", expand=True, slider=True)
    row = layout.row()
    row.column(align=True).prop(data, "edge_color", expand=True, slider=True)
    layout.row().prop(data, "edge_weight", slider=True)
    row = layout.row()
    row.column(align=True).prop(data, "texture_factor", expand=True, slider=True)
    row.column(align=True).prop(
        data,
        "sphere_texture_factor",
        expand=True,
        slider=True,
    )
    row.column(align=True).prop(
        data,
        "toon_texture_factor",
        expand=True,
        slider=True,
    )


def _draw_uv_vertex_groups(layout, root, morph):
    FnModel, _Model = _mmd_api()
    morph_module = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.core.morph"
    )
    found = False
    for mesh_object in FnModel.iterate_mesh_objects(root):
        axes = sorted(
            {
                axis
                for _vertex_group, _name, axis in (
                    morph_module.FnMorph.get_uv_morph_vertex_groups(
                        mesh_object,
                        morph.name,
                    )
                )
            }
        )
        if not axes:
            continue
        found = True
        row = layout.row(align=True)
        row.prop(mesh_object, UV_DETAIL_SELECTED_PROPERTY, text="")
        row.label(text=mesh_object.name, icon="MESH_DATA")
        row.label(text=" / ".join(axes))
    if not found:
        layout.label(text="模型中没有对应的 UV Vertex Group", icon="INFO")


def _draw_uv_details(layout, root, morph):
    controls = layout.column(align=True)
    row = controls.row(align=True)
    row.operator("surface_proxy.view_uv_morph", text="查看")
    row.operator("surface_proxy.clear_uv_morph_preview", text="清除")
    row = controls.row(align=True)
    row.operator("mmd_tools.edit_uv_morph", text="编辑")
    row.operator("mmd_tools.apply_uv_morph", text="应用")

    settings = layout.column()
    if morph.data:
        settings.row().prop(morph, "data_type", expand=True)
    row = settings.row()
    if morph.data_type == "VERTEX_GROUP":
        row.prop(morph, "vertex_group_scale", text="比例")
    else:
        row.label(text=f"UV 偏移 ({len(morph.data)})")
    row.prop(morph, "uv_index", text="UV 层")
    row.operator("mmd_tools.morph_offset_remove", text="", icon="X").all = True
    if morph.data_type == "VERTEX_GROUP":
        _draw_uv_vertex_groups(layout, root, morph)
    else:
        _draw_offset_list(layout, morph, "SPX_UL_UVMorphOffsets")


def _draw_bone_details(layout, root, morph):
    _FnModel, Model = _mmd_api()
    armature = Model(root).armature()
    if armature is None:
        layout.label(text="找不到 Armature", icon="ERROR")
        return

    row = layout.row(align=True)
    row.operator("mmd_tools.view_bone_morph", text="查看")
    row.operator("mmd_tools.apply_bone_morph", text="应用")
    row.operator("mmd_tools.clear_bone_morph_view", text="清除")
    row = layout.row(align=True)
    row.operator(
        SPX_OT_ConvertWeightedBoneMorphToVertexMorph.bl_idname,
        text="转换为 Vertex Morph",
        icon="SHAPEKEY_DATA",
    )
    row.operator(
        SPX_OT_BatchConvertWeightedBoneMorphsToVertexMorphs.bl_idname,
        text="",
        icon="LINENUMBERS_ON",
    )

    _draw_offset_list(layout, morph, "SPX_UL_BoneMorphOffsets")
    if not morph.data:
        return
    data = morph.data[morph.active_data]
    layout.row(align=True).prop_search(data, "bone", armature.pose, "bones", text="骨骼")
    if data.bone:
        row = layout.row(align=True)
        row.operator("mmd_tools.select_bone_morph_offset_bone", text="选择")
        row.operator("mmd_tools.edit_bone_morph_offset", text="编辑")
        row.operator("mmd_tools.apply_bone_morph_offset", text="更新")
    row = layout.row()
    row.column(align=True).prop(data, "location")
    row.column(align=True).prop(data, "rotation")


def _draw_active_details(layout, context, root):
    if not (0 <= root.spx_morph_active_index < len(root.spx_morph_states)):
        return
    state = root.spx_morph_states[root.spx_morph_active_index]
    morph = _morph_by_uid(root, state.morph_type, state.uid)
    if morph is None:
        return
    box = layout.box()
    row = box.row(align=True)
    row.prop(morph, "name", text="日文名")
    row.prop(morph, "name_e", text="英文名")
    box.prop(morph, "category", text="分类")
    if state.morph_type == "vertex_morphs":
        FnModel, _Model = _mmd_api()
        found = False
        for mesh_object in FnModel.iterate_mesh_objects(root):
            shape_keys = getattr(mesh_object.data, "shape_keys", None)
            key_block = shape_keys.key_blocks.get(morph.name) if shape_keys else None
            if key_block is None:
                continue
            found = True
            row = box.row(align=True)
            row.prop(mesh_object, VERTEX_DETAIL_SELECTED_PROPERTY, text="")
            select = row.operator(
                "surface_proxy.select_vertex_morph_object",
                text=mesh_object.name,
                icon="MESH_DATA",
            )
            select.root_name = root.name
            select.object_name = mesh_object.name
            select.morph_uid = state.uid
            row.prop(key_block, "value", text="", slider=True)
        if not found:
            box.label(text="模型中没有同名 ShapeKey", icon="INFO")
        else:
            _draw_detail_selection_buttons(box)
        return
    if state.morph_type == "material_morphs":
        _draw_material_details(box, morph)
    elif state.morph_type == "uv_morphs":
        _draw_uv_details(box, root, morph)
    elif state.morph_type == "bone_morphs":
        _draw_bone_details(box, root, morph)
    elif state.morph_type == "group_morphs":
        _draw_offset_list(box, morph, "SPX_UL_GroupMorphOffsets")
        box.operator(
            SPX_OT_CollectSelectedMorphsIntoGroup.bl_idname,
            text="将其它 Tab 勾选 Morph 加入当前组",
            icon="IMPORT",
        )
        if morph.data:
            data = morph.data[morph.active_data]
            box.prop(data, "morph_type", text="Morph 类型")
            box.prop_search(
                data,
                "name",
                root.mmd_root,
                data.morph_type,
                text="Morph",
            )
            box.prop(data, GROUP_FACTOR_PROXY_PROPERTY, text="权重")


def draw_morph_editor(layout, context):
    settings = context.scene.surface_proxy_creator
    root = _find_root(context, settings)
    row = layout.row(align=True)
    row.prop(settings, "morph_editor_root", text="MMD 模型")
    row.operator("surface_proxy.refresh_morph_editor", text="", icon="FILE_REFRESH")
    if root is None:
        layout.label(text="请选择 MMD 模型或模型内对象", icon="INFO")
        return
    if not _morph_states_are_current(root):
        _schedule_morph_state_refresh(root)
        if not _morph_state_structure_is_current(root):
            layout.label(text="正在读取 Morph…", icon="TIME")
            return
    clipboard_box = layout.box()
    clipboard_row = clipboard_box.row(align=True)
    clipboard_row.operator(
        SPX_OT_CopySelectedMorphsToClipboard.bl_idname,
        text="复制勾选 Morph",
        icon="COPYDOWN",
    )
    clipboard_row.operator(
        SPX_OT_PasteMorphsFromClipboard.bl_idname,
        text="从剪贴板粘贴 Morph",
        icon="PASTEDOWN",
    )
    tabs = layout.row(align=True)
    tabs.prop(settings, "morph_editor_type", expand=True)
    controls = layout.row(align=True)
    controls.prop(
        settings,
        "morph_editor_show_japanese",
        text="日文名",
        toggle=True,
    )
    controls.prop(
        settings,
        "morph_editor_show_english",
        text="英文名",
        toggle=True,
    )
    controls.prop(settings, "morph_editor_search", text="", icon="VIEWZOOM")
    row = layout.row()
    row.template_list(
        "SPX_UL_MorphEditor",
        "",
        root,
        "spx_morph_states",
        root,
        "spx_morph_active_index",
        rows=12,
    )
    buttons = row.column(align=True)
    buttons.operator("surface_proxy.add_morph", text="", icon="ADD")
    buttons.operator("surface_proxy.remove_selected_morphs", text="", icon="REMOVE")
    buttons.separator(factor=0.5)
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="TRIA_UP_BAR").action = "TOP"
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="TRIA_UP").action = "UP"
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="TRIA_DOWN").action = "DOWN"
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="TRIA_DOWN_BAR").action = "BOTTOM"
    buttons.separator(factor=0.5)
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="ANCHOR_TOP").action = "BEFORE"
    buttons.operator("surface_proxy.reorder_morphs", text="", icon="ANCHOR_BOTTOM").action = "AFTER"
    tab_states = [
        state
        for state in root.spx_morph_states
        if state.morph_type == settings.morph_editor_type
    ]
    selected_count = sum(state.selected for state in tab_states)
    layout.label(
        text=(
            f"总 Morph：{len(root.spx_morph_states)} 项；"
            f"当前页：{len(tab_states)} 项；已勾选：{selected_count} 项"
        )
    )
    selection = layout.row(align=True)
    selection.operator("surface_proxy.select_morphs", text="全选").action = "ALL"
    selection.operator("surface_proxy.select_morphs", text="全不选").action = "NONE"
    selection.operator("surface_proxy.select_morphs", text="反选").action = "INVERT"
    selection.operator(SPX_OT_SelectMorphInterval.bl_idname, text="区间选组")
    selection.operator(
        SPX_OT_CleanSelectedEmptyMorphs.bl_idname,
        text="清理",
        icon="TRASH",
    )
    if settings.morph_editor_type == "vertex_morphs":
        layout.prop(
            settings,
            "morph_editor_shapekey_cleanup_threshold",
            text="形态键清理阈值",
        )
    name_tools = layout.row(align=True)
    name_tools.operator(
        SPX_OT_CopyMorphJapaneseNamesToEnglish.bl_idname,
        text="日文名同步到英文名",
        icon="FORWARD",
    )
    name_tools.operator(
        SPX_OT_TranslateMorphNamesWithAI.bl_idname,
        text="AI翻译",
        icon="WORLD",
    )
    name_tools.operator(
        SPX_OT_MorphAISettings.bl_idname,
        text="",
        icon="PREFERENCES",
    )
    if RUNTIME_ERROR_PROPERTY in root:
        layout.label(text=str(root[RUNTIME_ERROR_PROPERTY]), icon="ERROR")
    layout.label(
        text="首次调整或 VMD 导入时按需建立 Runtime；Material Output 接管只安装一次",
        icon="INFO",
    )
    _draw_active_details(layout, context, root)


def register_settings(settings_cls):
    annotations = settings_cls.__annotations__
    annotations["morph_editor_root"] = PointerProperty(
        name="MMD 模型",
        type=bpy.types.Object,
        poll=_root_poll,
    )
    annotations["morph_editor_type"] = EnumProperty(
        name="Morph 类型",
        items=MORPH_TYPES,
        default="material_morphs",
        update=_morph_editor_type_updated,
    )
    annotations["morph_editor_search"] = StringProperty(name="搜索")
    annotations["morph_editor_show_japanese"] = BoolProperty(
        name="日文名",
        default=True,
    )
    annotations["morph_editor_show_english"] = BoolProperty(
        name="英文名",
        default=True,
    )
    annotations["morph_editor_shapekey_cleanup_threshold"] = FloatProperty(
        name="形态键清理阈值",
        description=(
            "清理勾选 Vertex Morph 时，若某 ShapeKey 在网格上所有顶点相对 Basis "
            "的最大位移不超过该值，则删除该 ShapeKey（单位：米，物体局部坐标）"
        ),
        default=1.0e-4,
        min=0.0,
        soft_max=1.0e-2,
        precision=6,
        step=0.01,
    )


@persistent
def _morph_frame_change(_scene, _depsgraph=None):
    for root in bpy.data.objects:
        if getattr(root, "mmd_type", "") != "ROOT" or not hasattr(
            root, "spx_morph_states"
        ):
            continue
        if root.spx_morph_states:
            evaluate_morph_root(root)


def _get_group_morph_factor(offset):
    return offset.factor


def _set_group_morph_factor(offset, value):
    offset.factor = value
    root = offset.id_data
    if (
        root is not None
        and getattr(root, "mmd_type", "") == "ROOT"
        and hasattr(root, "spx_morph_states")
        and root.spx_morph_states
    ):
        evaluate_morph_root(root)


def _register_group_morph_factor_proxy():
    morph_properties = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.properties.morph"
    )
    item_type = morph_properties.GroupMorphOffset
    if not hasattr(item_type, GROUP_FACTOR_PROXY_PROPERTY):
        setattr(
            item_type,
            GROUP_FACTOR_PROXY_PROPERTY,
            FloatProperty(
                name="权重",
                description="Group Morph 中目标 Morph 的权重",
                soft_min=0.0,
                soft_max=1.0,
                precision=3,
                step=0.1,
                get=_get_group_morph_factor,
                set=_set_group_morph_factor,
            ),
        )


def _unregister_group_morph_factor_proxy():
    morph_properties = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.properties.morph"
    )
    item_type = morph_properties.GroupMorphOffset
    if hasattr(item_type, GROUP_FACTOR_PROXY_PROPERTY):
        delattr(item_type, GROUP_FACTOR_PROXY_PROPERTY)


def _register_detail_selection_properties():
    global _DETAIL_SELECTION_REGISTRATIONS
    morph_properties = importlib.import_module(
        "bl_ext.blender_org.mmd_tools.properties.morph"
    )
    registrations = (
        (bpy.types.Object, VERTEX_DETAIL_SELECTED_PROPERTY),
        (bpy.types.Object, UV_DETAIL_SELECTED_PROPERTY),
        (morph_properties.MaterialMorphData, DETAIL_SELECTED_PROPERTY),
        (morph_properties.UVMorphOffset, DETAIL_SELECTED_PROPERTY),
        (morph_properties.BoneMorphData, DETAIL_SELECTED_PROPERTY),
        (morph_properties.GroupMorphOffset, DETAIL_SELECTED_PROPERTY),
    )
    for item_type, property_name in registrations:
        if not hasattr(item_type, property_name):
            setattr(
                item_type,
                property_name,
                BoolProperty(
                    name="选择",
                    description="选择该详情项，供后续批量操作使用",
                    default=False,
                ),
            )
    _DETAIL_SELECTION_REGISTRATIONS = registrations


def _unregister_detail_selection_properties():
    global _DETAIL_SELECTION_REGISTRATIONS
    for item_type, property_name in reversed(_DETAIL_SELECTION_REGISTRATIONS):
        if hasattr(item_type, property_name):
            delattr(item_type, property_name)
    _DETAIL_SELECTION_REGISTRATIONS = ()


def register_services():
    _register_detail_selection_properties()
    _register_group_morph_factor_proxy()
    bpy.types.Object.spx_morph_states = bpy.props.CollectionProperty(
        type=SPX_MorphState
    )
    bpy.types.Object.spx_morph_active_index = IntProperty(
        name="活动 Morph",
        min=0,
        default=0,
        update=_active_morph_index_updated,
    )
    if _morph_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_morph_frame_change)
    if (
        _migrate_existing_vmd_morph_animations_on_load
        not in bpy.app.handlers.load_post
    ):
        bpy.app.handlers.load_post.append(
            _migrate_existing_vmd_morph_animations_on_load
        )
    if not bpy.app.timers.is_registered(
        _migrate_existing_vmd_morph_animations_timer
    ):
        bpy.app.timers.register(
            _migrate_existing_vmd_morph_animations_timer,
            first_interval=0.0,
        )
    retry_interval = _install_vmd_io_hooks()
    if (
        retry_interval is not None
        and not bpy.app.timers.is_registered(_install_vmd_io_hooks)
    ):
        bpy.app.timers.register(
            _install_vmd_io_hooks,
            first_interval=retry_interval,
        )


def unregister_services():
    _unregister_group_morph_factor_proxy()
    if bpy.app.timers.is_registered(_install_vmd_io_hooks):
        bpy.app.timers.unregister(_install_vmd_io_hooks)
    _remove_vmd_io_hooks()
    if bpy.app.timers.is_registered(
        _migrate_existing_vmd_morph_animations_timer
    ):
        bpy.app.timers.unregister(_migrate_existing_vmd_morph_animations_timer)
    if (
        _migrate_existing_vmd_morph_animations_on_load
        in bpy.app.handlers.load_post
    ):
        bpy.app.handlers.load_post.remove(
            _migrate_existing_vmd_morph_animations_on_load
        )
    if _morph_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_morph_frame_change)
    if hasattr(bpy.types.Object, "spx_morph_active_index"):
        del bpy.types.Object.spx_morph_active_index
    if hasattr(bpy.types.Object, "spx_morph_states"):
        del bpy.types.Object.spx_morph_states
    _unregister_detail_selection_properties()


CLASSES = (
    SPX_MorphAIAddonPreferences,
    SPX_MorphState,
    SPX_OT_SetMorphValue,
    SPX_UL_MorphEditor,
    SPX_UL_MaterialMorphOffsets,
    SPX_UL_UVMorphOffsets,
    SPX_UL_BoneMorphOffsets,
    SPX_UL_GroupMorphOffsets,
    SPX_OT_RefreshMorphEditor,
    SPX_OT_CopySelectedMorphsToClipboard,
    SPX_OT_PasteMorphsFromClipboard,
    SPX_OT_AddMorph,
    SPX_OT_RemoveSelectedMorphs,
    SPX_OT_CleanSelectedEmptyMorphs,
    SPX_OT_SelectMorphs,
    SPX_OT_SelectMorphInterval,
    SPX_OT_CopyMorphJapaneseNamesToEnglish,
    SPX_OT_TranslateMorphNamesWithAI,
    SPX_OT_MorphAISettings,
    SPX_OT_ReorderMorphs,
    SPX_OT_ConvertWeightedBoneMorphToVertexMorph,
    SPX_OT_BatchConvertWeightedBoneMorphsToVertexMorphs,
    SPX_OT_AddMorphOffset,
    SPX_OT_RemoveMorphOffset,
    SPX_OT_ReorderMorphOffsets,
    SPX_OT_ApplyMaterialMorphPreset,
    SPX_OT_SelectMorphDetails,
    SPX_OT_CollectSelectedMorphsIntoGroup,
    SPX_OT_ViewUVMorph,
    SPX_OT_ClearUVMorphPreview,
    SPX_OT_SelectVertexMorphObject,
)
