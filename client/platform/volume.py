import json
import re
import shutil
import subprocess

from fastapi import HTTPException

# the volume of this machine's own audio output (PulseAudio, ALSA or PipeWire), not mpv's

VOLUME_SOCKET = "runtime/volume.socket"


# Percentage the volume changes by on each volume up/down request.
VOLUME_STEP = 2



async def _control_volume(action: str):
    """Control volume using the most appropriate Linux audio system"""
    
    # Check what audio systems are available
    amixer_available = shutil.which("amixer") is not None
    pactl_available = shutil.which("pactl") is not None
    wpctl_available = shutil.which("wpctl") is not None
    
    # Try different audio systems in order of preference
    # For WSL, prefer PulseAudio over ALSA since ALSA usually fails

    response = None

    if pactl_available:
        try:
            response = await _volume_pulseaudio(action)
        except Exception as e:
            print(f"pactl failed: {e}")
            
    if amixer_available and response is None:
        try:
            response = await _volume_amixer(action)
        except Exception as e:
            print(f"amixer failed (expected in WSL): {e}")
            
    if wpctl_available and response is None:
        try:
            response = await _volume_wireplumber(action)
        except Exception as e:
            print(f"wpctl failed: {e}")

    if not response:
        raise HTTPException(status_code=500, detail=f"No supported audio system found or all failed. Available: amixer={amixer_available}, pactl={pactl_available}, wpctl={wpctl_available}")

    as_str = json.dumps(response)
    with open(VOLUME_SOCKET, "w") as fp:
        fp.write(as_str)

    return response


async def _volume_amixer(action: str):
    """Control volume using ALSA amixer (most common on Raspberry Pi)"""
    mixer = "Master"

    try:
        if action in ("up", "down"):
            # changing the volume brings the sound back, like a TV
            subprocess.run(["amixer", "sset", mixer, "unmute"], capture_output=True, text=True, check=True)
        if action == "up":
            # Check current volume before increasing
            get_status = subprocess.run(
                ["amixer", "sget", mixer],
                capture_output=True, text=True, check=True
            )
            current_vol_match = re.search(r'\[(\d+)%\]', get_status.stdout)
            current_vol = int(current_vol_match.group(1)) if current_vol_match else 0

            # Cap at 100%
            if current_vol >= 100:
                return {"action": action, "method": "amixer", "status": "capped", "message": "Volume already at maximum (100%)", "volume": "100%"}
            elif current_vol > 100 - VOLUME_STEP:
                # Set to exactly 100% if we're close
                cmd = ["amixer", "sset", mixer, "100%"]
                message = "Volume set to maximum (100%)"
            else:
                cmd = ["amixer", "sset", mixer, f"{VOLUME_STEP}%+"]
                message = f"Volume increased by {VOLUME_STEP}%"
        elif action == "down":
            cmd = ["amixer", "sset", mixer, f"{VOLUME_STEP}%-"]
            message = f"Volume decreased by {VOLUME_STEP}%"
        elif action == "mute":
            # For mute, we need to check current state and toggle
            # First get current mute status
            get_status = subprocess.run(
                ["amixer", "sget", mixer],
                capture_output=True, text=True, check=True
            )
            # Check if currently muted - look for [off] in output
            is_muted = "[off]" in get_status.stdout

            # Toggle: if muted, unmute; if unmuted, mute
            mute_action = "unmute" if is_muted else "mute"
            cmd = ["amixer", "sset", mixer, mute_action]
            message = f"Mute {'off' if is_muted else 'on'}"
        else:
            raise ValueError(f"Invalid action: {action}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Try to extract volume level from amixer output
        volume_level = _extract_amixer_volume(result.stdout)
        return {"action": action, "method": "amixer", "status": "success", "message": message, "volume": volume_level}

    except subprocess.CalledProcessError:
        # If Master doesn't work, try PCM
        try:
            mixer = "PCM"
            if action == "up":
                # Check current volume before increasing
                get_status = subprocess.run(
                    ["amixer", "sget", mixer],
                    capture_output=True, text=True, check=True
                )
                current_vol_match = re.search(r'\[(\d+)%\]', get_status.stdout)
                current_vol = int(current_vol_match.group(1)) if current_vol_match else 0

                # Cap at 100%
                if current_vol >= 100:
                    return {"action": action, "method": "amixer", "status": "capped", "message": "Volume already at maximum (100%)", "volume": "100%"}
                elif current_vol > 100 - VOLUME_STEP:
                    # Set to exactly 100% if we're close
                    cmd = ["amixer", "sset", mixer, "100%"]
                    message = "Volume set to maximum (100%)"
                else:
                    cmd = ["amixer", "sset", mixer, f"{VOLUME_STEP}%+"]
                    message = f"Volume increased by {VOLUME_STEP}%"
            elif action == "down":
                cmd = ["amixer", "sset", mixer, f"{VOLUME_STEP}%-"]
                message = f"Volume decreased by {VOLUME_STEP}%"
            elif action == "mute":
                # For mute with PCM, check current state and toggle
                get_status = subprocess.run(
                    ["amixer", "sget", mixer],
                    capture_output=True, text=True, check=True
                )
                is_muted = "[off]" in get_status.stdout
                mute_action = "unmute" if is_muted else "mute"
                cmd = ["amixer", "sset", mixer, mute_action]
                message = f"Mute {'off' if is_muted else 'on'}"

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            volume_level = _extract_amixer_volume(result.stdout)
            return {"action": action, "method": "amixer", "status": "success", "message": f"{message} (PCM)", "volume": volume_level}
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"ALSA amixer failed: {e.stderr}")


async def _volume_pulseaudio(action: str):
    """Control volume using PulseAudio pactl"""
    try:
        if action in ("up", "down"):
            # changing the volume brings the sound back, like a TV
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], capture_output=True, text=True, check=True)
        if action == "up":
            # Check current volume before increasing
            current_volume_str = await _get_pulseaudio_volume()
            current_vol_match = re.search(r'(\d+)%', current_volume_str)
            current_vol = int(current_vol_match.group(1)) if current_vol_match else 0

            # Cap at 100% (PulseAudio uses 65536 as 100%)
            if current_vol >= 100:
                return {"action": action, "method": "pulseaudio", "status": "capped", "message": "Volume already at maximum (100%)", "volume": "100%"}
            elif current_vol > 100 - VOLUME_STEP:
                # Set to exactly 100%
                cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"]
                message = "Volume set to maximum (100%)"
            else:
                cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{VOLUME_STEP}%"]
                message = f"Volume increased by {VOLUME_STEP}%"
        elif action == "down":
            cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{VOLUME_STEP}%"]
            message = f"Volume decreased by {VOLUME_STEP}%"
        elif action == "mute":
            cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
            message = "Mute toggled"
        else:
            raise ValueError(f"Invalid action: {action}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Get current volume and mute status after the change
        if action == "mute":
            volume_level = await _get_pulseaudio_mute_status()
        else:
            volume_level = await _get_pulseaudio_volume()

        return {"action": action, "method": "pulseaudio", "status": "success", "message": message, "volume": volume_level}

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"PulseAudio pactl failed: {e.stderr}")


async def _volume_wireplumber(action: str):
    """Control volume using WirePlumber wpctl (newer PipeWire systems)"""
    try:
        if action in ("up", "down"):
            # changing the volume brings the sound back, like a TV
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], capture_output=True, text=True, check=True)
        if action == "up":
            # wpctl has a built-in limit option
            # Using --limit=1.0 caps volume at 100%
            cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{VOLUME_STEP / 100}+", "--limit=1.0"]
            message = f"Volume increased by {VOLUME_STEP}%"
        elif action == "down":
            cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{VOLUME_STEP / 100}-"]
            message = f"Volume decreased by {VOLUME_STEP}%"
        elif action == "mute":
            cmd = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
            message = "Mute toggled"
        else:
            raise ValueError(f"Invalid action: {action}")

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Try to get current volume from wpctl
        volume = await _get_wireplumber_volume()

        return {"action": action, "method": "wireplumber", "status": "success", "message": message, "volume": volume}

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"WirePlumber wpctl failed: {e.stderr}")


def _extract_amixer_volume(output: str) -> str:
    """Extract volume percentage and mute status from amixer output"""
    try:
        # Look for pattern like [75%] in the amixer output
        match = re.search(r'\[(\d+)%\]', output)
        volume = match.group(1) if match else "??"

        # Check if muted - look for [off] in output
        is_muted = "[off]" in output

        if is_muted:
            return f"MUTED ({volume}%)"
        else:
            return f"{volume}%"
    except:
        return "unknown"


async def _get_pulseaudio_volume() -> str:
    """Get current volume from PulseAudio"""
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )
        
        # PulseAudio output looks like: Volume: front-left: 65536 /  100% / 0.00 dB,   front-right: 65536 /  100% / 0.00 dB
        match = re.search(r'(\d+)%', result.stdout)
        if match:
            return f"{match.group(1)}%"
        return "unknown"
    except:
        return "unknown"


async def _get_pulseaudio_mute_status() -> str:
    """Get current mute status and volume from PulseAudio"""
    try:
        # Check mute status
        mute_result = subprocess.run(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )

        # Get volume
        volume_result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, check=True
        )

        # Parse mute status - output is like "Mute: yes" or "Mute: no"
        is_muted = "yes" in mute_result.stdout.lower()

        # Parse volume
        volume_match = re.search(r'(\d+)%', volume_result.stdout)
        volume = volume_match.group(1) if volume_match else "??"

        if is_muted:
            return f"MUTED ({volume}%)"
        else:
            return f"{volume}%"

    except:
        return "MUTE"


async def _get_wireplumber_volume() -> str:
    """Get current volume from WirePlumber"""
    try:
        result = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True, text=True, check=True
        )

        # wpctl output looks like: "Volume: 0.75" or "Volume: 0.75 [MUTED]"
        # Convert decimal to percentage
        match = re.search(r'Volume:\s+([\d.]+)', result.stdout)
        if match:
            volume_decimal = float(match.group(1))
            volume_percent = int(volume_decimal * 100)

            # Check if muted
            is_muted = "[MUTED]" in result.stdout

            if is_muted:
                return f"MUTED ({volume_percent}%)"
            else:
                return f"{volume_percent}%"
        return "unknown"
    except:
        return "unknown"
