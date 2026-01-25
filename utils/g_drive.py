import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from utils.g_drive_authentication import authenticate_user
from django.conf import settings

# Folder ID in Google Drive where files will be uploaded
DRIVE_FOLDER_ID = settings.GDRIVE_FOLDER_ID

def upload_to_drive_oauth(django_file, file_name):
    # 1. Authenticate as the user
    creds = authenticate_user()
    service = build("drive", "v3", credentials=creds)

    # Prepare file metadata
    file_metadata = {
        "name": file_name,
        "parents": [DRIVE_FOLDER_ID],
    }

    # Convert Django file to a stream
    media = MediaIoBaseUpload(
        io.BytesIO(django_file.read()), mimetype=django_file.content_type, resumable=True
    )

    uploaded_file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = uploaded_file.get("id")

    # 4. Make file publicly accessible 
    # The user (you) is now the owner, so this permission is simple.
    service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()

    print(f"\n✅ Uploaded file ID: {file_id}")
    print(f"🔗 Public URL: https://drive.google.com/file/d/{file_id}/view")

     # Return public URL
    return f"https://drive.google.com/file/d/{file_id}/view"

def download_from_drive_oauth(file_id):
    # 1. Authenticate and build service
    creds = authenticate_user()
    service = build("drive", "v3", credentials=creds)

    # 2. Request the file content
    request = service.files().get_media(fileId=file_id)

    # 3. Use an io.BytesIO buffer to hold the downloaded data
    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)

    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}%.")

    # 4. Move the pointer to the beginning of the buffer
    file_buffer.seek(0)

    # Return the buffer content (or you could save it to a local file)
    return file_buffer
