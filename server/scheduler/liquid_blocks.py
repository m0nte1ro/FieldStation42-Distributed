import datetime
import os.path
import random

from shared import timings
from server.scheduler.reel_cutter import ReelCutter
from shared.rundown import BlockPlanEntry
from server.catalog.media_processor import MediaProcessor


class LiquidBlock:
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None):
        self.content = content
        # the requested starting time
        self.start_time = start_time
        # the expected/requested end time
        self.end_time = end_time
        if title is None and type(content) is not list:
            self.title = content.title
        else:
            self.title = title
        self.reel_blocks = None
        self.plan = None
        

        self.break_info = break_info if break_info else {}
        
        self.sequence_key = None

        if break_info:
            #print("break info: ", break_info)
            self.start_bump = break_info.get("start_bump", None)
            self.end_bump = break_info.get("end_bump", None)
            self.bump_override = break_info.get("bump_dir", None)
            self.commercial_override = break_info.get("commercial_dir", None)
        
        self.break_strategy = break_strategy

        # set by liquid_schedule before make_plan() is called
        # index 0=current, 1=next, 2=next-next, 3=next-next-next
        self.lookahead = []

    def __str__(self):
        content = os.path.basename(self.content.path)
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title} - {content}"

    def content_duration(self):
        return self.content.duration

    def playback_duration(self):
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        return self.playback_duration() - self.content_duration()

    @staticmethod
    def clip_break_points(break_points, max_breaks, content_duration):
        # ensure start ordering
        break_points = MediaProcessor.calc_black_segments(break_points, content_duration)

        # Handle edge cases
        if max_breaks <= 0 or len(break_points) == 0:
            return []

        if len(break_points) <= max_breaks:
            return break_points

        # Merge adjacent chapters to create evenly-distributed segments
        # This ensures no content is skipped, just fewer commercial breaks
        max_breaks = int(max_breaks)

        # Calculate which chapter boundaries to keep as break insertion points
        # For max_breaks segments, we need (max_breaks - 1) commercial breaks
        num_breaks = max_breaks - 1

        # Select evenly-distributed break positions
        step = (len(break_points) - 1) / num_breaks if num_breaks > 0 else 0
        break_indices = []
        for i in range(1, max_breaks):  # Start from 1, not 0 (skip the first chapter start)
            index = round(i * step)
            if index not in break_indices and index < len(break_points):
                break_indices.append(index)

        # Create merged segments by combining chapters between selected break points
        merged_segments = []
        segment_start_idx = 0

        for break_idx in break_indices:
            # Merge all chapters from segment_start_idx to break_idx into one segment
            merged_segment = {
                "chapter_start": break_points[segment_start_idx]["chapter_start"],
                "chapter_end": break_points[break_idx]["chapter_start"],
            }
            merged_segments.append(merged_segment)
            segment_start_idx = break_idx

        # Add the final segment (from last break to end)
        final_segment = {
            "chapter_start": break_points[segment_start_idx]["chapter_start"],
            "chapter_end": break_points[-1]["chapter_end"],
        }
        merged_segments.append(final_segment)

        return merged_segments

    def make_plan(self, catalog):
        # a programme always plays whole: whatever fills the rest of the block comes after it
        self.break_strategy = "end"
        diff = self.playback_duration() - self.content_duration()

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump["duration"]

        if self.end_bump:
            diff -= self.end_bump["duration"]

        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise (ValueError(err))

        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time,
                diff,
                commercial_dir=self.commercial_override,
                bump_dir=self.bump_override,
                lookahead=self.lookahead,
                break_strategy=self.break_strategy,
            )
        else:
            self.reel_blocks = []

        self.plan = ReelCutter.cut_reels_into_base(
            base_clip=self.content,
            reel_blocks=self.reel_blocks,
            base_offset=0,
            base_duration=self.content_duration(),
            break_strategy=self.break_strategy,
            start_bump=self.start_bump,
            end_bump=self.end_bump,
        )


class LiquidClipBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None):
        if type(content) is list:
            super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        else:
            raise (TypeError(f"LiquidClipBlock required content of type list. Got {type(content)} instead"))

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title}"

    def content_duration(self):
        dur = 0
        for clip in self.content:
            dur += clip.duration
        return dur

    def make_plan(self, catalog):
        self.plan = []
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump["duration"]

        if self.end_bump:
            diff -= self.end_bump["duration"]

        # calculate desired number of breaks based on break_duration
        strict_count = None
        break_duration = self.break_info.get("break_duration", None)
        if break_duration is None:
            break_duration = catalog.config.get("break_duration", None)

        if break_duration and break_duration > 0 and diff > 2:
            # calculate how many breaks we want based on total buffer time and break_duration
            strict_count = max(1, int(diff / break_duration))

        self.reel_blocks = None
        if diff < -2:
            err = f"Schedule logic error: duration requested {self.playback_duration()} is less than content {self.content_duration()}"
            err += f" for show named: {self.content.title}"
            raise (ValueError(err))
        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time, diff, commercial_dir=self.commercial_override, bump_dir=self.bump_override,
                strict_count=strict_count,
                lookahead=self.lookahead,
                break_strategy=self.break_strategy,
            )
        else:
            self.reel_blocks = []

        self.plan = ReelCutter.cut_reels_into_clips(
            self.content, self.reel_blocks, self.break_strategy, self.start_bump, self.end_bump
        )

class LiquidWebBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None, sign_off=None):
        super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.sign_off = sign_off

    def make_plan(self, catalog):
        self.plan = []
        remaining = (self.end_time - self.start_time).total_seconds()
        for _c in [self.sign_off, self.content]:
            if _c is None or remaining <= 0:
                continue
            duration = min(float(_c.duration), remaining)
            self.plan.append(BlockPlanEntry(_c.path, 0, duration, content_type=_c.content_type, media_type=_c.media_type))
            remaining -= duration


class LiquidOffAirBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None, sign_off=None):
        super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.sign_off = sign_off

    def make_plan(self, catalog):
        self.plan = []
        current_mark = self.start_time
        first_loop = True
        while current_mark < self.end_time:
            # only show sign_off on first loop
            if self.sign_off and first_loop:
                _content = self.sign_off
            else:
                _content = self.content
            first_loop = False
            duration = float(_content.duration)
            current_mark += datetime.timedelta(seconds=duration)
            datetime.timedelta()
            if current_mark > self.end_time:
                # then we will clip it to end at end time
                delta = current_mark - self.end_time
                duration -= delta.total_seconds()

            self.plan.append(BlockPlanEntry(_content.path, 0, duration, content_type=_content.content_type, media_type=_content.media_type))


class LiquidLoopBlock(LiquidBlock):
    def __init__(self, content, start_time, end_time, title=None, break_strategy="standard", break_info=None, shuffle=False):
        super().__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.shuffle = shuffle

    def __str__(self):
        return f"{self.start_time.strftime('%m/%d %H:%M')} - {self.end_time.strftime('%H:%M')} - {self.title} - LOOP"

    def make_plan(self, catalog):
        if not self.content:
            raise ValueError("LiquidLoopBlock requires content")
        entries = []
        keep_going = True
        current_mark: datetime.datetime = self.start_time
        next_mark: datetime.datetime = None
        current_index = 0
        random.shuffle(self.content)
        while keep_going:
            clip = self.content[current_index]
            next_mark = current_mark + datetime.timedelta(seconds=clip.duration)
            duration = clip.duration
            if next_mark < self.end_time:
                current_index += 1
                if current_index >= len(self.content):
                    current_index = 0
                    if self.shuffle:
                        random.shuffle(self.content)

            else:
                keep_going = False
                duration = (self.end_time - current_mark).total_seconds()

            entries.append(BlockPlanEntry(clip.path, 0, duration, content_type=clip.content_type, media_type=clip.media_type))

            current_mark = next_mark
        self.plan = entries


class ReelBlock:
    def __init__(self, start_bump=None, comms=[], end_bump=None):
        self.start_bump = start_bump
        self.comms = comms
        self.end_bump = end_bump

    def __str__(self):
        return f"ReelBlock: {self.duration} {len(self.comms)}"

    @property
    def duration(self):
        dur = 0
        if self.start_bump is not None:
            dur += self.start_bump.duration
        for comm in self.comms:
            dur += comm.duration
        if self.end_bump is not None:
            dur += self.end_bump.duration
        return dur

    def make_plan(self):
        entries = []
        if self.start_bump is not None:
            entries.append(BlockPlanEntry(self.start_bump.path, 0, self.start_bump.duration, content_type="bump", media_type=self.start_bump.media_type))
        for comm in self.comms:
            entries.append(BlockPlanEntry(comm.path, 0, comm.duration, content_type="commercial", media_type=comm.media_type))
        if self.end_bump is not None:
            entries.append(BlockPlanEntry(self.end_bump.path, 0, self.end_bump.duration, content_type="bump", media_type=self.end_bump.media_type))
        return entries
