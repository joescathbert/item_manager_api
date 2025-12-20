import requests
from django.http import StreamingHttpResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Define the allowed media domains to prevent your proxy from being abused
ALLOWED_MEDIA_DOMAINS = [
    'media.redgifs.com',
    # Add other media domains you might proxy, e.g., 'v.redd.it', 'gfycat.com'
]

@require_http_methods(["GET"])
def media_proxy_view(request):
    """
    Proxies media requests from external URLs to bypass cross-origin restrictions.
    Expects a query parameter: ?url=https://media.redgifs.com/...
    """
    external_url = request.GET.get('url')

    if not external_url:
        return HttpResponseBadRequest("Missing 'url' parameter.")

    try:
        # 1. Basic URL validation
        parsed_url = urlparse(external_url)
        if parsed_url.netloc not in ALLOWED_MEDIA_DOMAINS:
            return HttpResponseBadRequest("Invalid or disallowed media domain.")

        # 2. Make the streaming request to the external server
        # Crucially, we do NOT send the client's 'Referer' header.
        response = requests.get(
            external_url,
            stream=True,
            timeout=10, # Set a timeout
            headers={
                # Optional: Spoof the Referer header to the source site (often necessary)
                'Referer': f'https://{parsed_url.netloc}/',
                # Copy the User-Agent if needed, or set a generic one
                'User-Agent': request.headers.get('User-Agent', 'Django-Media-Proxy')
            }
        )
        response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)

    except requests.exceptions.RequestException as e:
        print(f"Proxy failed for {external_url}: {e}")
        return HttpResponse("Could not retrieve media file.", status=502)

    # 3. Define the generator for streaming the response chunks
    def file_iterator(file_handle, chunk_size=8192):
        yield from file_handle.iter_content(chunk_size)

    # 4. Stream the response back to the client
    # Copy essential headers to let the client (Angular/Browser) know what it's receiving
    
    # Check if we have Content-Type and Content-Length
    content_type = response.headers.get('Content-Type', 'application/octet-stream')
    content_length = response.headers.get('Content-Length')

    proxy_response = StreamingHttpResponse(
        file_iterator(response),
        content_type=content_type,
        status=response.status_code
    )

    if content_length:
        proxy_response['Content-Length'] = content_length

    # Important: Disable cache headers for the video stream
    proxy_response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    proxy_response['Pragma'] = 'no-cache'
    proxy_response['Expires'] = '0'
    
    return proxy_response