import os
import requests
import sys
from pathlib import Path


def download_file(url, destination):
    """Download a file from a URL to the destination path."""
    try:
        print(f"Downloading {url} to {destination}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 Kibibyte
        downloaded = 0
        
        with open(destination, 'wb') as file:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                file.write(data)
                
                # Print progress
                done = int(50 * downloaded / total_size) if total_size > 0 else 0
                sys.stdout.write(f"\r[{'=' * done}{' ' * (50 - done)}] {downloaded/1024/1024:.1f}/{total_size/1024/1024:.1f} MB")
                sys.stdout.flush()
                
        print("\nDownload complete!")
        return True
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return False


def main():
    """Download MobileNet SSD model files for person detection."""
    # Define model directory
    model_dir = Path(__file__).parent / "models"
    model_dir.mkdir(exist_ok=True)
    
    # Model files to download
    files = {
        "MobileNetSSD_deploy.prototxt": "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt",
        "MobileNetSSD_deploy.caffemodel": "https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"
    }
    
    # Download each file if it doesn't exist
    success = True
    for filename, url in files.items():
        destination = model_dir / filename
        
        if destination.exists():
            print(f"{filename} already exists, skipping download.")
        else:
            result = download_file(url, destination)
            if not result:
                success = False
    
    if success:
        print("\nAll model files downloaded successfully!")
        print(f"Files saved to: {model_dir}")
    else:
        print("\nSome downloads failed.")


if __name__ == "__main__":
    main()