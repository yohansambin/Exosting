import asyncio
import json
import os
from pathlib import Path

import aiofiles
from ignis import utils
from ignis.command_manager import CommandManager
from ignis.css_manager import CssInfoPath, CssManager

from exosting.user_settings import user_settings

from .send_notification import send_notification

css_manager = CssManager.get_default()
command_manager = CommandManager.get_default()


class Wallpaper:
    SCHEMES = (
        "content",
        "expressive",
        "fidelity",
        "fruit-salad",
        "monochrome",
        "neutral",
        "rainbow",
        "tonal-spot",
    )

    @staticmethod
    def get_mode(active: bool) -> str:
        return "dark" if active else "light"

    @staticmethod
    def apply_matugen(path: str, scheme: str, mode: str) -> None:
        if scheme not in Wallpaper.SCHEMES:
            scheme = Wallpaper.SCHEMES[-1]

        asyncio.create_task(
            utils.exec_sh_async(
                f"matugen image -t scheme-{scheme} "
                f"'{path}' -m '{mode}' --source-color-index 0"
            )
        )

    @staticmethod
    def update_gtk_theme() -> None:
        theme = (
            utils.exec_sh("gsettings get org.gnome.desktop.interface gtk-theme")
            .stdout.strip()
            .strip("'")
        )

        source = Path("/usr/share/themes") / theme / "gtk-4.0" / "gtk.css"
        target = Path.home() / ".config/gtk-4.0/theme.css"

        if not source.is_file():
            raise FileNotFoundError(f"GTK4 theme CSS not found: {source}")

        css = f'@import url("{source}");\n@import url("colors.css");'

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(css, encoding="utf-8")

    @staticmethod
    def reload_css(delay: int = 3000) -> None:
        Wallpaper.generatePreviews()
        utils.Timeout(
            ms=delay,
            target=css_manager.reload_all_css,
        )

    @staticmethod
    @command_manager.command(name="set-wallpaper")
    def setWall(path) -> None:
        colorScheme = user_settings.appearance.wallcolors.color_scheme
        mode = Wallpaper.get_mode(user_settings.appearance.wallcolors.dark_mode)

        Wallpaper.apply_matugen(path, colorScheme, mode)

        send_notification("Wallpaper Set!", str(os.path.basename(path)))
        user_settings.appearance.wallcolors.set_wallpaper_path(path)

        Wallpaper.reload_css()

    @staticmethod
    def setColors(colorScheme) -> None:
        path = user_settings.appearance.wallcolors.wallpaper_path
        mode = Wallpaper.get_mode(user_settings.appearance.wallcolors.dark_mode)

        Wallpaper.apply_matugen(path, colorScheme, mode)
        Wallpaper.update_gtk_theme()

        user_settings.appearance.wallcolors.set_color_scheme(colorScheme)
        Wallpaper.reload_css()

    @staticmethod
    def setDarkMode(active: bool) -> None:
        mode = Wallpaper.get_mode(active)
        colorScheme = user_settings.appearance.wallcolors.color_scheme
        path = user_settings.appearance.wallcolors.wallpaper_path

        if active and "lightthemeoverrides" in css_manager.list_css_info_names():
            css_manager.remove_css("lightthemeoverrides")
        elif "lightthemeoverrides" not in css_manager.list_css_info_names():
            css_manager.apply_css(
                CssInfoPath(
                    name="lightthemeoverrides",
                    path=os.path.expanduser(
                        "~/.config/ignis/exosting/styles/lightthemeoverrides.scss"
                    ),
                    compiler_function=lambda path: utils.sass_compile(path=path),
                    priority="user",
                )
            )

        Wallpaper.apply_matugen(path, colorScheme, mode)

        theme = "Orchis-Dark" if active else "Orchis-Light"
        utils.exec_sh(f"gsettings set org.gnome.desktop.interface gtk-theme '{theme}'")
        Wallpaper.update_gtk_theme()

        asyncio.create_task(
            utils.exec_sh_async(
                f"gsettings set org.gnome.desktop.interface color-scheme 'prefer-{mode}'"
            )
        )

        user_settings.appearance.wallcolors.set_dark_mode(active)
        Wallpaper.reload_css(2000)

    @staticmethod
    def generatePreviews() -> None:
        async def do_generate() -> None:
            path = user_settings.appearance.wallcolors.wallpaper_path
            if not path or not os.path.exists(path):
                return

            current_mode = (
                "dark" if user_settings.appearance.wallcolors.dark_mode else "light"
            )
            current_scheme = user_settings.appearance.wallcolors.color_scheme
            if current_scheme not in Wallpaper.SCHEMES:
                current_scheme = Wallpaper.SCHEMES[-1]

            scss_content = ""

            tasks_palette = []
            for scheme in Wallpaper.SCHEMES:
                command = f"matugen image -t scheme-{scheme} '{path}' -m {current_mode} --json hex --dry-run --source-color-index 0"
                tasks_palette.append(utils.exec_sh_async(command))

            tasks_theme = []
            for mode in ["light", "dark"]:
                command = f"matugen image -t scheme-{current_scheme} '{path}' -m {mode} --json hex --dry-run --source-color-index 0"
                tasks_theme.append(utils.exec_sh_async(command))

            all_results = await asyncio.gather(*(tasks_palette + tasks_theme))

            results_palette = all_results[: len(Wallpaper.SCHEMES)]
            results_theme = all_results[len(Wallpaper.SCHEMES) :]

            for i, result in enumerate(results_palette):
                scheme = Wallpaper.SCHEMES[i]
                if result.stdout:
                    try:
                        data = json.loads(result.stdout)
                        # matugen-bin
                        if current_mode in data.get("colors", {}):
                            for color_name, color_value in data["colors"][
                                current_mode
                            ].items():
                                variable_name = (
                                    f"palette-{scheme}-{color_name.replace('_', '-')}"
                                )
                                scss_content += f"${variable_name}: {color_value};\n"
                        # matugen-git (as of r107.ga49399b)
                        else:
                            for color_name, values in data["colors"].items():
                                if current_mode in values:
                                    color_value = values[current_mode]["color"]
                                    variable_name = f"palette-{scheme}-{color_name.replace('_', '-')}"
                                    scss_content += (
                                        f"${variable_name}: {color_value};\n"
                                    )
                    except json.JSONDecodeError as e:
                        stderr = result.stderr if result.stderr else ""
                        print(
                            f"Failed to decode json for palette {scheme}: {stderr} | {e}"
                        )

            for i, result in enumerate(results_theme):
                mode = ["light", "dark"][i]
                if result.stdout:
                    try:
                        # matugen-bin
                        data = json.loads(result.stdout)
                        if mode in data.get("colors", {}):
                            for color_name, color_value in data["colors"][mode].items():
                                variable_name = (
                                    f"theme-{mode}-{color_name.replace('_', '-')}"
                                )
                                scss_content += f"${variable_name}: {color_value};\n"
                        # matugen-git (as of r107.ga49399b)
                        else:
                            for color_name, values in data["colors"].items():
                                if mode in values:
                                    color_value = values[mode]["color"]
                                    variable_name = (
                                        f"theme-{mode}-{color_name.replace('_', '-')}"
                                    )
                                    scss_content += (
                                        f"${variable_name}: {color_value};\n"
                                    )
                    except json.JSONDecodeError as e:
                        stderr = result.stderr if result.stderr else ""
                        print(
                            f"Failed to decode json for theme preview {mode}: {stderr} | {e}"
                        )
            if not scss_content:
                return
            scss_file_path = os.path.expanduser(
                "~/.config/ignis/exosting/styles/preview-colors.scss"
            )
            os.makedirs(os.path.dirname(scss_file_path), exist_ok=True)
            async with aiofiles.open(scss_file_path, "w") as f:
                await f.write(scss_content)

        asyncio.create_task(do_generate())
