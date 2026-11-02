from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from src.services.spotify_service import spotify_service
from src.services.flac_downloader_service import flac_downloader_service
from src.services.gdrive_service import gdrive_service

router = APIRouter(prefix="/api/music", tags=["music"])

class PlaylistRequest(BaseModel):
    url: str

def process_download_task(spotify_url: str, filename: str):
    """
    Background task to download track and upload to Google Drive.
    """
    try:
        # Download
        file_path = flac_downloader_service.download_track(spotify_url)
        
        # Upload
        gdrive_service.upload_file(file_path, filename)
        
        # Cleanup
        flac_downloader_service.cleanup(file_path)
    except Exception as e:
        print(f"Error processing {spotify_url}: {str(e)}")

@router.post("/playlist")
async def process_playlist(request: PlaylistRequest, background_tasks: BackgroundTasks):
    try:
        tracks = spotify_service.get_playlist_tracks(request.url)
        
        # Dispatch background tasks for downloading and uploading each track
        for track in tracks:
            if track['url']:
                filename = f"{track['artists'][0]} - {track['name']}.flac"
                background_tasks.add_task(process_download_task, track['url'], filename)
                
        return {"message": f"Processing {len(tracks)} tracks in the background.", "tracks": tracks}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
