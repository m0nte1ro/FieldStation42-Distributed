import os

# FS42_WINDOW=1280x720 plays the TV in a borderless window of that size at the screen's top-left corner
# instead of fullscreen (for trying a client on a desktop). Everything on screen follows it: the
# picture, the OSD and overlays, the guide and web pages.


def window_size(env=os.environ):
    value = env.get("FS42_WINDOW", "").strip().lower()
    if not value:
        return None
    try:
        width, height = (int(n) for n in value.split("x"))
    except ValueError:
        raise SystemExit(f"FS42_WINDOW must be a size like 1280x720, not {value!r}")
    return width, height


def mpv_window_options(size):
    if not size:
        return {"fs": True}
    width, height = size
    return {"fs": False, "geometry": f"{width}x{height}+0+0", "border": False}


def tv_rect(screen, env=os.environ):
    """Where the TV is drawn: the window when there is one, else the whole screen."""
    from PySide6.QtCore import QRect

    size = window_size(env)
    if size:
        return QRect(0, 0, *size)
    return screen.geometry() if screen else QRect(0, 0, 1920, 1080)
