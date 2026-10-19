import glob
import os


# guide channel settings; pure config, so loading stations never needs Tk
class GuideWindowConf:
    def __init__(self, w=720, h=480):
        self.fullscreen = True

        self.width = w
        self.height = h

        self.top_bg = "blue3"
        self.bottom_bg = "blue4"

        self.pad = 10

        self.messages = [
            "Hello FieldStation42\nGuide preview",
            "Cheers!\nFrom us to you!",
            "FieldStation42 Guide\nOn cable mode.",
        ]
        self.message_rotation_rate = 10
        self.message_fg = "white"
        self.message_font_family = "Arial"
        self.message_font_size = 25

        self.images = []

        self.network_font_family = "Arial"
        self.network_font_size = 12
        self.network_width_divisor = 6.0

        self.schedule_font_family = "Arial"
        self.schedule_font_size = 12
        self.schedule_highlight_fg = "yellow"
        self.schedule_fg = "white"

        self.schedule_border_width = 4
        self.schedule_border_relief = "raised"

        self.footer_messages = ["You are watching FieldStation42", "Now with cable mode."]
        self.footer_height = 50

        self.schedule_row_count = 3
        self.schedule_col_count = 3

        self.play_sound = False
        self.sound_to_play = None
        self.normalize_titles = True

        self.scroll_speed = 1.0

        # Ratio of top section height to total height (0.0 to 1.0)
        # 0.5 = 50/50 split, 0.3 = 30% top / 70% bottom, etc.
        self.top_section_ratio = 0.5

        # Row height constraints for responsive sizing
        self.target_row_height = 60  # Target height for schedule rows
        self.min_row_height = 40     # Minimum height for schedule rows
        self.max_row_height = 80     # Maximum height for schedule rows

        self._calc_internals()

    def _calc_internals(self):
        self.half_h = self.height / 2
        self.half_w = self.width / 2

        # Calculate section heights based on configurable ratio
        self.top_section_height = self.height * self.top_section_ratio
        self.bottom_section_height = self.height * (1.0 - self.top_section_ratio)

        self.network_w = self.width / self.network_width_divisor
        self.sched_w = (self.width - self.network_w) / self.schedule_col_count

        # Calculate responsive row height with constraints
        # First, calculate how much space is available for rows (minus the header row)
        available_height = self.bottom_section_height

        # Try to use target row height for header + rows
        total_rows = 1 + self.schedule_row_count  # 1 header + schedule rows
        calculated_height = available_height / total_rows

        # Constrain row height to min/max bounds
        self.sched_h = max(self.min_row_height, min(self.max_row_height, calculated_height))

        # Calculate how many visible rows we can actually fit
        self.visible_row_count = int((available_height - self.sched_h) / self.sched_h)

        self._message_font = (self.message_font_family, self.message_font_size)
        self._schedule_font = (self.schedule_font_family, self.schedule_font_size)
        self._network_font = (self.network_font_family, self.network_font_size)
        self._message_rotation_rate = self.message_rotation_rate * 1000

    def merge_config(self, to_merge):
        for key in to_merge:
            if hasattr(self, key):
                setattr(self, key, to_merge[key])
        self._calc_internals()

    def check_config(self, merge_conf):
        """Note: this should only be called from the startup checker since it merges the conf again"""
        self.merge_config(merge_conf)
        to_check = self.images.copy()

        # Check sound_to_play - can be a string (file or directory) or a list of files
        if self.play_sound and self.sound_to_play:
            if isinstance(self.sound_to_play, list):
                # It's a list - check each file
                for sound_file in self.sound_to_play:
                    to_check.append(sound_file)
            elif isinstance(self.sound_to_play, str):
                # It's a string - could be a file or directory
                if os.path.isdir(self.sound_to_play):
                    # Directory path - check if it has any mp3 files
                    mp3_files = glob.glob(os.path.join(self.sound_to_play, "*.mp3"))
                    if not mp3_files:
                        errors = [f"Guide channel directory {self.sound_to_play} exists but contains no .mp3 files"]
                        return errors
                else:
                    # Single file path - add to check list
                    to_check.append(self.sound_to_play)

        errors = []
        for fp in to_check:
            if not os.path.exists(fp):
                err = f"Guide channel config references a file named {fp} but it does not exist on disk"
                errors.append(err)

        # check that its fullscreen, or else that width and height are specified
        if not self.fullscreen:
            if not self.width or not self.height:
                err = """Guide channel fullscreen is set to false, but width or height is not speficied.
                If fullscreen is not set to true, please set both width and height in pixels.
                """
                errors.append(err)
        return errors
