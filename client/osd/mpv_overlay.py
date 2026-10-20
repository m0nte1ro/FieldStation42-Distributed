import mmap
import os

from PySide6.QtGui import QImage

# mpv overlays are numbered 0-63 and drawn in that order: static at the bottom, the OSD over it
STATIC_ID = 0
OVERLAY_ID = 1


class MpvOverlay:
    """The OSD drawn into shared memory and shown by mpv over the video (mpv's overlay-add).

    It has no window of its own, so it looks the same on X11, Wayland or mpv straight on the screen,
    and needs no compositor. Two buffers: a frame is drawn into the one mpv isn't showing, and mpv is
    only told when the picture changed.
    """

    def __init__(self, mpv, path):
        self.mpv = mpv
        self.path = path
        self.size = None
        self._images = []
        self._back = 0
        self._front = None

    def _allocate(self, width, height):
        self._release()
        stride = width * 4
        frame = stride * height
        with open(self.path, "w+b") as f:
            f.truncate(2 * frame)
            self._memory = mmap.mmap(f.fileno(), 2 * frame)
        # premultiplied ARGB32 is BGRA in memory on little-endian machines: mpv's "bgra"
        self._views = [memoryview(self._memory)[i * frame:(i + 1) * frame] for i in (0, 1)]
        self._images = [QImage(view, width, height, stride, QImage.Format_ARGB32_Premultiplied) for view in self._views]
        self._blank = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        self._blank.fill(0)
        self.size = (width, height)
        self._back, self._front = 0, None

    def _release(self):
        if not self._images:
            return
        if self._front is not None:
            self.mpv.command("overlay-remove", OVERLAY_ID)
        self._images = []
        for view in self._views:
            view.release()
        self._memory.close()

    def frame(self):
        """A cleared image the size of mpv's picture to draw the OSD on."""
        size = (int(self.mpv.osd_width or 0), int(self.mpv.osd_height or 0))
        if size != self.size and min(size) > 0:
            self._allocate(*size)
        if not self._images:
            return None
        image = self._images[self._back]
        image.fill(0)
        return image

    def present(self):
        """Show the drawn frame, if it differs from what mpv shows now."""
        if not self._images:
            return
        image = self._images[self._back]
        if image == self._blank:
            if self._front is not None:
                self.mpv.command("overlay-remove", OVERLAY_ID)
                self._front = None
            return
        if self._front is not None and image == self._images[self._front]:
            return
        width, height = self.size
        self.mpv.command("overlay-add", OVERLAY_ID, 0, 0, self.path, self._back * width * height * 4, "bgra",
                         width, height, width * 4)
        self._front, self._back = self._back, 1 - self._back

    def close(self):
        self._release()
        if os.path.exists(self.path):
            os.remove(self.path)


class StaticOverlay:
    """TV static over the picture while mpv tunes a channel or waits for data.

    A few small frames of noise, made once; mpv scales the one shown to the whole picture on the GPU,
    and a different frame each tick makes it move.
    """

    WIDTH, HEIGHT, FRAMES = 320, 180, 8

    def __init__(self, mpv, path):
        self.mpv = mpv
        self.path = path
        self._frame_bytes = self.WIDTH * self.HEIGHT * 4
        with open(path, "w+b") as f:
            f.truncate(self.FRAMES * self._frame_bytes)
            self._memory = mmap.mmap(f.fileno(), self.FRAMES * self._frame_bytes)
        for i in range(self.FRAMES):
            noise = QImage(os.urandom(self.WIDTH * self.HEIGHT), self.WIDTH, self.HEIGHT, self.WIDTH,
                           QImage.Format_Grayscale8).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            start = i * self._frame_bytes
            self._memory[start:start + self._frame_bytes] = bytes(noise.constBits())[:self._frame_bytes]
        self._next = 0
        self._shown = False

    def show(self, on):
        if on:
            width, height = int(self.mpv.osd_width or 0), int(self.mpv.osd_height or 0)
            if min(width, height) <= 0:
                return
            self.mpv.command("overlay-add", STATIC_ID, 0, 0, self.path, self._next * self._frame_bytes, "bgra",
                             self.WIDTH, self.HEIGHT, self.WIDTH * 4, width, height)
            self._next = (self._next + 1) % self.FRAMES
            self._shown = True
        elif self._shown:
            self.mpv.command("overlay-remove", STATIC_ID)
            self._shown = False
