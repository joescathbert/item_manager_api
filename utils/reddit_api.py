import requests
import re

# --- Configuration ---
# Reddit requires a User-Agent header for API requests.
# Replace 'YourApp/1.0' with a unique name for your application.
# (This is a good practice to avoid being blocked.)
HEADERS = {
    'User-Agent': 'LinkCollectorApp/1.0 (by /u/YourRedditUsername)'
}

# --- Core Function ---

def get_reddit_link_details(reddit_url):
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
        return {
            'original_url': reddit_url,
            'url': direct_url,
            'domain_name': domain
        }

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error fetching data: {e}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network or Connection Error: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

    return None
