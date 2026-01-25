import threading
import yt_dlp
import subprocess
import json
from urllib.parse import urlparse
from typing import Dict, Any

def get_media_details(url: str) -> Dict[str, Any]:
    result = {"original_url": url, "media": []}

    # We use a list to store the yt-dlp result so the thread can modify it
    ext_data = {"info": None, "error": None}

    def target():
        try:
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                # 'extract_flat': True, # Start flat for speed
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ext_data["info"] = ydl.extract_info(url, download=False)
        except Exception as e:
            ext_data["error"] = e

    # Start the thread
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=20) # <--- STRICT 10 SECOND LIMIT

    if thread.is_alive():
        print(f"!!! yt-dlp timed out for {url}. Killing thread and moving to gallery-dl.")
        # We can't actually 'kill' a thread easily, but we can ignore it 
        # and move on, letting it finish in the background.
    elif ext_data["info"]:
        # If yt-dlp finished and found something
        entries = ext_data["info"].get('entries', [ext_data["info"]])
        print(json.dumps(ext_data["info"], indent=2))
        for entry in entries:
            # Basic check to see if this specific entry is a video
            if entry.get('vcodec') != 'none' or 'formats' in entry:
                video_data = process_video_entry(entry)
                if video_data:
                    result["media"].append(video_data)

    # 2. Image Extraction (gallery-dl) - Handles galleries and mixed media
    try:
        cmd = ["gallery-dl", "-j", url]
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if process.returncode == 0:
            data = json.loads(process.stdout)
            for entry in data:
                # gallery-dl entries look like: [index, "URL", {metadata}]
                # We MUST ensure the second element is a string (the URL)
                if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], str):
                    image_url = entry[1]
                    parsed_image_url = urlparse(image_url)
                    image_url_domain = parsed_image_url.netloc.lower()

                    # Ignore non-image links
                    if image_url_domain not in ['pbs.twimg.com', 'i.redd.it']:
                        continue

                    # Ignore non-http links or profile pictures if they creep in
                    if not image_url.startswith("http"):
                        continue

                    # Twitter-specific HD transformation
                    hd = image_url
                    if "twimg.com" in image_url:
                        if "format=" in image_url: # New Twitter URL style
                            # replaces name=small/medium/large with name=orig
                            import re
                            hd = re.sub(r'name=[^&]+', 'name=orig', image_url)
                        else: # Old Twitter URL style
                            hd = image_url.split(":")[0] + ":orig"

                    result["media"].append({
                        "hd_url": hd,
                        "sd_url": image_url,
                        "media_type": "image"
                    })
    except Exception as e:
        print(f"Gallery-dl error: {e}") 

    return result

def process_video_entry(entry: Dict) -> Dict:
    """Extracts HD (best) and SD (worst) resolutions from a single entry."""
    formats = entry.get('formats', [])
    # Filter for mp4-compatible or mixed formats
    video_formats = [f for f in formats if f.get('vcodec') != 'none']

    if video_formats:
        # Calculate the 'quality' based on the shortest dimension
        for f in video_formats:
            w = f.get('width') or 0
            h = f.get('height') or 0
            f['short_side'] = min(w, h) if w and h else (h or w or 0)

        # Sort by that shortest side descending
        video_formats.sort(key=lambda x: x['short_side'], reverse=True)
        
        hd = video_formats[0]['url']
        
        # Target 600p as the standard SD threshold
        # If no format is <= 600p, take the lowest quality available
        sd_format = next((f for f in video_formats if f['short_side'] <= 600), video_formats[-1])
        sd = sd_format['url']

        return {
            "hd_url": hd,
            "sd_url": sd,
            "media_type": "video"
        }

    return None
