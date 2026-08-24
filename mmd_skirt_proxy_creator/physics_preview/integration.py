_MODEL_ARMATURE_RESOLVER = None
_SESSION_ADAPTER_FACTORY = None


def install(model_armature_resolver, session_adapter_factory):
    global _MODEL_ARMATURE_RESOLVER, _SESSION_ADAPTER_FACTORY
    if _MODEL_ARMATURE_RESOLVER is not None or _SESSION_ADAPTER_FACTORY is not None:
        raise RuntimeError("Physics preview integration is already installed")
    _MODEL_ARMATURE_RESOLVER = model_armature_resolver
    _SESSION_ADAPTER_FACTORY = session_adapter_factory


def uninstall(model_armature_resolver, session_adapter_factory):
    global _MODEL_ARMATURE_RESOLVER, _SESSION_ADAPTER_FACTORY
    if _MODEL_ARMATURE_RESOLVER is model_armature_resolver:
        _MODEL_ARMATURE_RESOLVER = None
    if _SESSION_ADAPTER_FACTORY is session_adapter_factory:
        _SESSION_ADAPTER_FACTORY = None


def resolve_model_armature(root):
    if _MODEL_ARMATURE_RESOLVER is None:
        return None
    return _MODEL_ARMATURE_RESOLVER(root)


def create_session_adapter(session):
    if _SESSION_ADAPTER_FACTORY is None:
        return None
    return _SESSION_ADAPTER_FACTORY(session)
