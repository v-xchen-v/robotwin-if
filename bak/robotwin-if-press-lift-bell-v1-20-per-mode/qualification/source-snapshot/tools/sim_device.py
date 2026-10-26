"""Explicit SAPIEN renderer binding for standalone serial probes."""


def pin_renderer():
    # SAPIEN 3's compatibility wrapper ignores the device keyword. Pin both the
    # C++ renderer and the scene RenderSystem, as in the successful serial suite.
    import sapien
    import sapien.pysapien.render
    from sapien.wrapper.scene import Scene
    device = sapien.Device("cuda:0")
    renderer, scene_init = sapien.SapienRenderer, Scene.__init__

    class PinnedRenderer(renderer):
        def __init__(self, **kwargs):
            sapien.pysapien.render.SapienRenderer.__init__(self, device)

    def init_scene(self, systems=None):
        if systems is None:
            systems = [sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device)]
        scene_init(self, systems)
        assert self.render_system.device.pci_string == device.pci_string

    sapien.SapienRenderer = PinnedRenderer
    Scene.__init__ = init_scene
    return device.pci_string
