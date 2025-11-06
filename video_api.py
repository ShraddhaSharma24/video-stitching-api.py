import os
import shutil
from pathlib import Path
from typing import List
import subprocess
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import tempfile

app = FastAPI(
    title="Video Stitching Agent API",
    description="API for stitching multiple video files together",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoStitcher:
    def stitch_videos_ffmpeg(self, video_paths: List[str], output_path: str,
                            method: str = "concat") -> str:
        if not video_paths:
            raise ValueError("No video paths provided")

        print(f"Stitching {len(video_paths)} videos...")

        if method == "concat":
            return self._concat_demuxer(video_paths, output_path)
        else:
            return self._concat_filter(video_paths, output_path)

    def _concat_demuxer(self, video_paths: List[str], output_path: str) -> str:
        # Create concat file in the same temp directory as output
        concat_file = output_path + "_concat_list.txt"
        with open(concat_file, 'w') as f:
            for video_path in video_paths:
                abs_path = os.path.abspath(video_path)
                f.write(f"file '{abs_path}'\n")

        cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file,
               '-c', 'copy', '-y', output_path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Video stitched successfully: {output_path}")
            # Clean up concat file
            os.remove(concat_file)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg concat failed: {e.stderr}")
            # Try filter method as fallback
            if os.path.exists(concat_file):
                os.remove(concat_file)
            return self._concat_filter(video_paths, output_path)

    def _concat_filter(self, video_paths: List[str], output_path: str) -> str:
        inputs = []
        filter_parts = []

        for i, video_path in enumerate(video_paths):
            inputs.extend(['-i', video_path])
            filter_parts.append(f'[{i}:v][{i}:a]')

        filter_complex = f"{''.join(filter_parts)}concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

        cmd = ['ffmpeg', *inputs, '-filter_complex', filter_complex,
               '-map', '[outv]', '-map', '[outa]',
               '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Video stitched successfully: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg filter failed: {e.stderr}")

stitcher = VideoStitcher()

@app.get("/")
async def root():
    return {
        "message": "Video Stitching Agent API",
        "version": "1.0.0",
        "endpoints": {
            "/stitch": "POST - Upload multiple video files to stitch",
            "/health": "GET - Check API health",
            "/docs": "GET - Interactive API documentation"
        },
        "instructions": "Visit /docs for interactive Swagger UI. Click 'Try it out' on /stitch endpoint, then click 'Add string item' multiple times to upload multiple videos."
    }

@app.get("/health")
async def health_check():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, text=True)
        ffmpeg_version = result.stdout.split('\n')[0]
        ffmpeg_available = True
    except:
        ffmpeg_version = "Not available"
        ffmpeg_available = False

    return {
        "status": "healthy" if ffmpeg_available else "degraded",
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_version": ffmpeg_version
    }

@app.post("/stitch", 
    summary="Stitch Multiple Videos",
    description="""
    Upload 2 or more video files to stitch them together.
    
    **In Swagger UI:** 
    1. Click 'Try it out'
    2. Click 'Choose File' to select your first video
    3. Click 'Add string item' button to add more file inputs
    4. Upload additional videos
    5. Click 'Execute'
    
    **Supported formats:** mp4, avi, mov, mkv, webm
    
    **Methods:**
    - `concat` (default): Fast, copies streams without re-encoding (requires same codec)
    - `filter`: Re-encodes videos (slower but works with different codecs)
    """)
async def stitch_videos(
    files: List[UploadFile] = File(..., description="Upload multiple video files (minimum 2)"),
    method: str = Form("concat", description="Stitching method: 'concat' or 'filter'")
):
    if len(files) < 2:
        raise HTTPException(
            status_code=400, 
            detail=f"At least 2 videos required for stitching. You uploaded {len(files)} file(s)."
        )

    # Create a unique temp directory for this request
    temp_dir = tempfile.mkdtemp(prefix="video_stitch_")
    print(f"\n=== NEW REQUEST ===")
    print(f"Temp directory: {temp_dir}")
    print(f"Processing {len(files)} files")
    
    video_paths = []

    try:
        # Validate and save uploaded files
        for i, file in enumerate(files):
            if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid file type: {file.filename}. Supported: mp4, avi, mov, mkv, webm"
                )

            file_path = os.path.join(temp_dir, f"input_{i:03d}_{file.filename}")
            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)
            video_paths.append(file_path)
            print(f"Saved input file {i+1}: {file.filename} ({len(content) / 1024:.2f} KB)")

        # Generate unique output filename
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"stitched_{unique_id}.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        print(f"Output file: {output_filename}")

        # Stitch videos
        result_path = stitcher.stitch_videos_ffmpeg(video_paths, output_path, method=method)

        # Verify the output file exists
        if not os.path.exists(result_path):
            raise Exception(f"Output file was not created: {result_path}")

        # Get file size and read content
        file_size = os.path.getsize(result_path)
        print(f"Reading output file: {file_size / 1024:.2f} KB")
        
        with open(result_path, 'rb') as f:
            video_content = f.read()
        
        print(f"Video content loaded into memory: {len(video_content)} bytes")
        
        # Clean up temp directory immediately
        print(f"Cleaning up temp directory: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("Cleanup complete\n")
        
        # Return the video content
        return Response(
            content=video_content,
            media_type="video/mp4",
            headers={
                "Content-Disposition": "attachment; filename=stitched_video.mp4",
                "X-Video-Count": str(len(files)),
                "X-Output-Size": str(file_size),
                "X-Method-Used": method,
                "X-Request-ID": unique_id
            }
        )

    except subprocess.CalledProcessError as e:
        print(f"ERROR: FFmpeg failed - {e.stderr}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Video processing failed: {str(e)}"
        )
    except Exception as e:
        print(f"ERROR: {str(e)}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Error: {str(e)}"
        )

# Run with: uvicorn video_api:app --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




