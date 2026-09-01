"""统一推理服务调度测试（不实例化模型权重）。"""

from vision_inspection.infer import HANDLERS, build_handlers


def test_registry_has_all_scenes():
    assert set(HANDLERS) == {"pipeline", "ppe"}


def test_build_handlers_classes_have_predict():
    # 不实例化（需要训练权重），只验证每个场景处理器类实现了 predict 接口
    for scene in ("pipeline", "ppe"):
        handler_cls = HANDLERS[scene]
        assert hasattr(handler_cls, "predict")
        assert callable(handler_cls.predict)


def test_unknown_scene_raises():
    import pytest

    with pytest.raises(KeyError):
        build_handlers("unknown_scene")
