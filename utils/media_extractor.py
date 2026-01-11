import requests
import re
import subprocess
from urllib.parse import urlparse
from utils.domain_urls import (REDGIFS_DOMAINS, REDDIT_DOMAINS, TWITTER_DOMAINS, REDDIT_MEDIA_DOMAINS,
    TWITTER_MEDIA_DOMAINS, IMGUR_DOMAINS)

# --- Configuration ---
# Reddit requires a User-Agent header for API requests.
# Replace 'YourApp/1.0' with a unique name for your application.
# (This is a good practice to avoid being blocked.)
HEADERS = {
    'User-Agent': 'LinkCollectorApp/1.0 (by /u/YourRedditUsername)'
}


def _get_media_url_with_reddit_api(reddit_url):
    """
    Fetches the JSON data for a Reddit post and extracts the direct URL,
    with a fallback for NSFW content which sometimes uses the 'preview' field.
    """
    json_url = reddit_url.rstrip('/') + '.json'

    try:
        response = requests.get(json_url, headers=HEADERS, timeout=10)
        response.raise_for_status() 
        data = response.json()

        # Access the main post data safely
        post_data = data[0]['data']['children'][0]['data']

        direct_url = None
        domain = None

        # --- Extraction Logic ---

        # 1. Primary Check: Standard secure_media for v.redd.it video
        if post_data.get('is_video') and post_data.get('secure_media'):
            video_data = post_data.get('secure_media', {}).get('reddit_video')
            if video_data:
                direct_url = video_data.get('fallback_url')
                domain = 'v.redd.it'
                print("✅ Detected as Standard v.redd.it Video")

        # 2. Secondary Check: Fallback for v.redd.it video using 'preview' (Common for NSFW/Secure)
        # We look for a source in the preview images that points to a video.
        if not direct_url and post_data.get('preview', {}).get('images'):
            preview_images = post_data['preview']['images'][0]

            # Check for a 'fallback' video source in the preview
            if preview_images.get('variants', {}).get('mp4'):
                # This path is often lower resolution but reliably present for videos
                direct_url = preview_images['variants']['mp4']['source']['url']
                domain = 'v.redd.it (Preview)'
                print("✅ Detected as Preview Video (NSFW/Secure Fallback)")

            # If no MP4 variant, check for the gif source (sometimes used for short videos)
            elif preview_images.get('variants', {}).get('gif'):
                direct_url = preview_images['variants']['gif']['source']['url']
                domain = 'v.redd.it (GIF Preview)'
                print("✅ Detected as GIF Preview")
                
            # Final attempt to find a fallback video URL if post is flagged as a video
            elif post_data.get('is_video') and post_data.get('media'):
                media_data = post_data.get('media', {}).get('reddit_video')
                if media_data:
                    direct_url = media_data.get('fallback_url')
                    domain = 'v.redd.it (Media Fallback)'
                    print("✅ Detected as Media Fallback Video")


        # 3. Tertiary Check: External Link
        if not direct_url and post_data.get('url_overridden_by_dest'):
            direct_url = post_data['url_overridden_by_dest']

            # Simple domain extraction
            match = re.search(r'//([a-zA-Z0-9.-]+)', direct_url)
            domain = match.group(1).replace('www.', '') if match else 'external-link'

            print("✅ Detected as External Link")

        # 4. Default Case
        if not direct_url:
            direct_url = reddit_url
            domain = 'www.reddit.com'
            print("⚠️ Detected as Text/Other/Unparseable Post Type")

        # --- Results ---
        return direct_url

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error fetching data: {e}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network or Connection Error: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

    return None

def _get_media_url_with_gallery_dl(url: str) -> str:
    cmd = ['gallery-dl', '--get-url', url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        media_url = result.stdout.strip()
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain in REDGIFS_DOMAINS:
            orig_media_url, mobile_media_url = media_url.split('\n|')
            media_url = mobile_media_url.strip()
        elif domain in REDDIT_DOMAINS:
            media_url = media_url.split('ytdl:')[-1].strip()
        elif domain in IMGUR_DOMAINS:
            pass
        elif domain in TWITTER_DOMAINS:
            pass
        return media_url
    except subprocess.CalledProcessError as e:
        print(f"Error using gallery-dl: {e.stderr}")
        return None

def get_reddit_link_details(reddit_url: str):
    reddit_media_url = _get_media_url_with_gallery_dl(reddit_url)
    result = {
        "original_url": reddit_url,
        "url": ""
    }
    if reddit_media_url:
        parsed = urlparse(reddit_media_url)
        domain = parsed.netloc.lower()
        if domain in REDGIFS_DOMAINS:
            redgifs_media_url = _get_media_url_with_gallery_dl(reddit_media_url)
            if redgifs_media_url:
                result["url"] = redgifs_media_url
        elif domain in IMGUR_DOMAINS:
            imgur_media_url = _get_media_url_with_gallery_dl(reddit_media_url)
            if imgur_media_url:
                result["url"] = imgur_media_url
        elif domain in REDDIT_MEDIA_DOMAINS:
            result["url"] = _get_media_url_with_reddit_api(reddit_url)
            # result["url"] = reddit_media_url + "/CMAF_720.mp4?source=fallback"

    return result

def get_twitter_link_details(twitter_url: str):
    twitter_media_url = _get_media_url_with_gallery_dl(twitter_url)
    result = {
        "original_url": twitter_url,
        "url": ""
    }
    if twitter_media_url:
        parsed = urlparse(twitter_media_url)
        domain = parsed.netloc.lower()
        if domain in TWITTER_MEDIA_DOMAINS:
            result["url"] = twitter_media_url

    return result
