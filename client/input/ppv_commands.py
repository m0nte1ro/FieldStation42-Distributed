import logging
import os

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from client.input.player_routes import connected_command_queue
from shared.stations.manager import StationManager

# the PPV page's commands act on this client's player; the listings come from the server
router = APIRouter(prefix="/ppv", tags=["ppv"])


class PlayFileRequest(BaseModel):
    """Request to play a file"""
    file_path: str

class PlayFileResponse(BaseModel):
    """Response from play_file endpoint"""
    success: bool
    message: str


@router.post("/{channel_number}/play_file", response_model=PlayFileResponse)
async def play_file(channel_number: int, play_request: PlayFileRequest, request: Request):
    """
    Play a file by sending a command to the player via the command queue.

    Args:
        channel_number: The channel number (for validation)
        play_request: PlayFileRequest containing the file path
        request: FastAPI Request object (to access app state)
    """
    logger = logging.getLogger("PPV_API")

    # Get station configuration to validate channel exists
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_number} not found"
        )

    # the file lives on the server; the player streams it from there
    command_queue = connected_command_queue(request)

    # Create the command to send to the player
    command = {
        "command": "play_file",
        "file_path": play_request.file_path
    }

    try:
        logger.info(f"Sending play command for file: {play_request.file_path}")

        # Put the command in the queue
        command_queue.put(command)

        logger.info(f"Successfully queued play command for: {play_request.file_path}")

        return PlayFileResponse(
            success=True,
            message=f"Play command sent for: {os.path.basename(play_request.file_path)}"
        )

    except Exception as e:
        logger.error(f"Error sending play command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send play command: {str(e)}"
        )

@router.post("/{channel_number}/key/{key_name}")
async def send_key(channel_number: int, key_name: str, request: Request):
    """Send a keypress to the PPV web channel."""
    allowed_keys = {"PageUp", "PageDown", "Enter"}
    if key_name not in allowed_keys:
        raise HTTPException(status_code=400, detail=f"Key must be one of: {allowed_keys}")
    command_queue = connected_command_queue(request)
    try:
        command_queue.put({"command": "web_key", "key": key_name})
        return {"success": True, "key": key_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
