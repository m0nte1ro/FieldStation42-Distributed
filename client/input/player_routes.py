from fastapi import APIRouter, Request, HTTPException
import json
import platform
from shared.stations.manager import StationManager
from client.platform.system_info import _get_cpu_info, _get_cpu_temperature, _get_memory_info
from client.platform.volume import _control_volume

router = APIRouter(prefix="/player", tags=["player"])


def connected_command_queue(request: Request):
    command_queue = request.app.state.player_command_queue
    if not command_queue:
        raise HTTPException(status_code=503, detail="Player command queue is not connected.")
    return command_queue

@router.get("/info")
async def get_info():
    """Get system information including CPU temp, memory usage, and CPU usage"""
    info = {}
    
    # Get CPU temperature
    temp_info = await _get_cpu_temperature()
    info.update(temp_info)
    
    # Get memory information
    memory_info = await _get_memory_info()
    info.update(memory_info)
    
    # Get CPU usage
    cpu_info = await _get_cpu_info()
    info.update(cpu_info)
    
    # Get system information
    try:
        info["system"] = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "hostname": platform.node()
        }
    except Exception:
        info["system"] = {"error": "unavailable"}
    
    return info







@router.get("/status")
async def get_player_status():
    status_socket = StationManager().server_conf["status_socket"]
    if status_socket:
        try:
            with open(status_socket, "r") as f:
                status_str = f.read().strip()
            return json.loads(status_str)
        except FileNotFoundError:
            return {"error": "Status socket file not found."}
    else:
        return {"error": "Status socket is not configured."}


@router.get("/status/queue_connected")
async def get_connected(request: Request):
    command_queue = request.app.state.player_command_queue
    if command_queue:
        return {"queue_connected": True}
    else:
        return {"queue_connected": False}

@router.get("/channels/{channel}")
async def player_channel(channel: str):
    command = {"command": "direct", "channel": -1}
    if channel.isnumeric():
        command["channel"] = int(channel)
    elif channel == "up":
        command["command"] = "up"
    elif channel == "down":
        command["command"] = "down"
    else:
        return {"error": "Invalid channel command. Use a number, 'up', or 'down'."}

    cs = StationManager().server_conf["channel_socket"]
    with open(cs, "w") as f:
        f.write(json.dumps(command))
    return {"command": command}


@router.post("/channels/guide")
async def show_guide(request:Request):
    command_queue = connected_command_queue(request)
    command_queue.put({"command": "guide"})
    return {"status" : "ok"}

@router.get("/commands/stop")
@router.post("/commands/stop")
async def player_stop(request: Request):
    command_queue = connected_command_queue(request)
    command_queue.put({"command": "exit"})
    return {"status": "stopped"}


async def _queue_mpv_command(request: Request, action: str):
    command_queue = connected_command_queue(request)
    command_queue.put({"command": "mpv_command", "action": action})
    return {"status": "ok", "command": "mpv_command", "action": action}


@router.get("/mpv/toggle-subtitles")
@router.post("/mpv/toggle-subtitles")
async def mpv_toggle_subtitles(request: Request):
    """Toggle subtitle visibility for the active mpv player."""
    return await _queue_mpv_command(request, "toggle_subtitles")


@router.get("/mpv/cycle-subtitles")
@router.post("/mpv/cycle-subtitles")
async def mpv_cycle_subtitles(request: Request):
    """Cycle through available subtitle tracks for the active mpv player."""
    return await _queue_mpv_command(request, "cycle_subtitles")


@router.get("/mpv/cycle-audio")
@router.post("/mpv/cycle-audio")
async def mpv_cycle_audio(request: Request):
    """Cycle through available audio tracks for the active mpv player."""
    return await _queue_mpv_command(request, "cycle_audio")


@router.post("/parental/digit/{digit}")
async def parental_digit(request: Request, digit: str):
    if not digit.isdigit() or len(digit) != 1:
        raise HTTPException(status_code=400, detail="Digit must be a single number.")

    command_queue = connected_command_queue(request)
    command_queue.put({"command": "parental_digit", "digit": digit})
    return {"handled": True}


@router.post("/parental/clear")
async def parental_clear(request: Request):
    command_queue = connected_command_queue(request)
    command_queue.put({"command": "parental_clear"})
    return {"handled": True}


@router.post("/ticker")
async def show_ticker(request: Request):
    command_queue = connected_command_queue(request)
    data = await request.json()
    command_queue.put({
        "command": "ticker", 
        "message": data.get("message", ""), 
        "header": data.get("header", "FS42"), 
        "style": data.get("style", "fieldstation"), 
        "iterations": data.get("iterations", 2)
    })
    return {"status": "success"}

@router.get("/volume/up")
@router.post("/volume/up")
async def volume_up():
    """Increase volume by VOLUME_STEP percent"""
    return await _control_volume("up")


@router.get("/volume/down")
@router.post("/volume/down")
async def volume_down():
    """Decrease volume by VOLUME_STEP percent"""
    return await _control_volume("down")


@router.get("/volume/mute")
@router.post("/volume/mute")
async def volume_mute():
    """Toggle mute on/off"""
    return await _control_volume("mute")















