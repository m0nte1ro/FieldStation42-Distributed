import datetime
import logging

from shared.stations.manager import StationManager
from server.scheduler.liquid_blocks import LiquidBlock
from shared.rundown import PlayPoint, ScheduleNotFound, ScheduleQueryNotInBounds, block_at, play_point
from server.catalog.catalog import ShowCatalog
from server.catalog.sequence_api import SequenceAPI
from server.scheduler.liquid_api import LiquidAPI
from server.scheduler.schedule_lock import schedule_write_lock


class LiquidManager(object):
    __we_are_all_one = {}
    _initialized = False
    station_configs = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __init__(self):
        self.__dict__ = self.__we_are_all_one
        if not self._initialized:
            self._initialized = True
            self.reload_schedules()

    def reload_schedules(self):
        # read the signature first: a write that lands during the load is picked up next time
        self._signature = LiquidAPI.signature()
        self.station_configs = StationManager().stations
        self._schedules = {}
        for station in self.station_configs:
            if station["network_type"] != "guide" and station["network_type"] != "streaming":
                _id = station["network_name"]
                self._schedules[_id] = LiquidAPI.get_blocks(station)

    @property
    def schedules(self):
        # the CLI and the console's build workers write schedules from other processes:
        # the database is the truth, this is only a copy until the table changes
        if LiquidAPI.signature() != self._signature:
            self.reload_schedules()
        return self._schedules

    def get_schedule_by_name(self, network_name):
        if network_name in self.schedules:
            return self.schedules[network_name]
        else:
            return None

    def reset_all_schedules(self):
        with schedule_write_lock():
            for station_config in self.station_configs:
                if station_config["_has_schedule"]:
                    logging.getLogger("liquid").info(f"Deleting schedules for {station_config['network_name']}")
                    self.reset_sequences(station_config)
                    LiquidAPI.delete_blocks(station_config)
        self.reload_schedules()

    def reset_schedule(self, station_config):
        with schedule_write_lock():
            if station_config["_has_schedule"]:
                logging.getLogger("liquid").info(f"Deleting schedules for {station_config['network_name']}")
                self.reset_sequences(station_config)
                LiquidAPI.delete_blocks(station_config)
        self.reload_schedules()

    def reset_sequences(self, station_config):
        logging.getLogger("liquid").info(f"Resetting sequences for {station_config['network_name']}")
        # get the catalog
        catalog = ShowCatalog(station_config)

        _blocks: list[LiquidBlock] = self.schedules.get(station_config["network_name"], [])

        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)
        _reaped = {}

        # make a sequence cache index
        all_seq_list = SequenceAPI.get_sequences_for_station(station_config)
        seq_index = {}
        for this_seq in all_seq_list:
            key = (this_seq.sequence_name, this_seq.tag_path)
            if key not in seq_index:
                seq_index[key] = this_seq

        for _block in _blocks:
            # are we to now yet?
            if _block.start_time >= today:
                # does it have a sequence and is that sequence in the catalog?

                if _block.sequence_key:
                    # make sure its in the store
                    #seq = SequenceAPI.get_sequence(
                    #    station_config, _block.sequence_key["sequence_name"], _block.sequence_key["tag_path"]
                    #)

                    # get the sequence from the index
                    skey = (_block.sequence_key["sequence_name"], _block.sequence_key["tag_path"])
                    seq = seq_index.get(skey, None)

                    # have we found it before?
                    if seq and skey not in _reaped:
                        # register that we found it
                        _reaped[skey] = _block
                        SequenceAPI.reset_by_episode_path(
                            station_config,
                            _block.sequence_key["sequence_name"],
                            _block.sequence_key["tag_path"],
                            _block.content.path,
                        )

        catalog._write_catalog()

    def get_extents(self, network_name):
        _id = network_name
        if _id not in self.schedules:
            raise (ValueError(f"Can't get extent for network named {network_name} - it does not exist."))
        _blocks = self.schedules[_id]
        if len(_blocks):
            return (_blocks[0].start_time, _blocks[-1].end_time)
        else:
            return (None, None)

    def get_summary(self):
        summary = ""
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summary += f"{_id} schedule extents: {s} to {e}\n"

        return summary

    def get_summary_json(self, network_name=None):
        if network_name:
            (s, e) = self.get_extents(network_name)
            return {"network_id": network_name, "start": s.isoformat() if s else None, "end": e.isoformat() if e else None}

        summaries = []
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summaries.append({"network_id": _id, "start": s.isoformat() if s else None, "end": e.isoformat() if e else None})

        return summaries

    def get_programming_block(self, network_name, when):
        self.get_extents(network_name)  # unknown station raises ValueError, as before
        return block_at(self.schedules[network_name], when)

    def get_play_point(self, network_name, when):
        station_conf = StationManager().station_by_name(network_name)
        blocks = self.schedules.get(network_name, [])
        return play_point(station_conf, blocks, when)

    def print_schedule(self, network_name, go_deep=False):
        for _block in self.schedules[network_name]:
            print(_block)
            if go_deep:
                # print(_block)
                current_mark = _block.start_time
                next_mark = current_mark
                for _entry in _block.plan:
                    next_mark = current_mark + datetime.timedelta(seconds=_entry.duration)
                    print(f"{_entry} start={current_mark.time()} end={next_mark.time()}")
                    current_mark = next_mark
