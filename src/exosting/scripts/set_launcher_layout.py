from exosting.modules.launcher.launcher import Launcher
from exosting.user_settings import user_settings


class LauncherLayout:
    launcher_instance: Launcher | None = None

    @classmethod
    def set_launcher_instance(cls, launcher: Launcher) -> None:
        cls.launcher_instance = launcher

    @classmethod
    def setLayout(cls, layout: str) -> None:
        if layout not in ["grid", "list"]:
            print(f"Invalid layout: {layout}. Must be 'grid' or 'list'.")
            return

        user_settings.interface.launcher.layout = layout
        if isinstance(cls.launcher_instance, Launcher):
            cls.launcher_instance._set_layout(layout)
