from dotenv import load_dotenv
from flask import current_app
import subprocess
import requests
import shutil
import json
import os
import re

load_dotenv(dotenv_path="/home/manav/base/SimplyServed/.env")
OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# normalises string to remove any special characters
def normalize(title):
    return re.sub(r'\W+', '', title.lower())

# loads progress from json from given path
def load_progress(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

# updates json file with given data
def save_progress(path, data):
    with open(path, "w") as f:
        json.dump(data, f)



# converts srt subtitles to vtt format (ideal for web use)
def convert_srt_to_vtt(srt_path):
    vtt_path = srt_path.replace(".srt", ".vtt")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", srt_path, vtt_path], check=True)
        os.remove(srt_path)
        print(f"Converted {srt_path} to {vtt_path}")
        return vtt_path
    except subprocess.CalledProcessError as e:
        print(f"Failed to convert subtitle: {e}")
        return None



# searches for subs using opensubtitles, downloads most popular subs to given save path
def search_and_download_subtitle(movie_name, save_path, language="en"):
    search_url = "https://api.opensubtitles.com/api/v1/subtitles"
    headers = {
        "Api-Key": OPENSUBTITLES_API_KEY,
        "User-Agent": "home server"
    }

    params = {
        "query": movie_name,
        "languages": language,
        "order_by": "download_count",
        "order_direction": "desc"
    }

    # sends request to search for subs
    response = requests.get(search_url, headers=headers, params=params, timeout=15)
    try:
        data = response.json()
    except Exception:
        print("Failed to decode JSON.")
        print("Status Code:", response.status_code)
        print("Response text:", response.text)
        return False

    if "data" not in data or not data["data"]:
        print(f"No subtitles found for movie: {movie_name}")
        return False

    best_match = data["data"][0]
    file_id = best_match["attributes"]["files"][0]["file_id"]

    # sends request to download subs
    download_url = "https://api.opensubtitles.com/api/v1/download"
    r = requests.post(download_url, headers=headers, json={"file_id": file_id}, timeout=15)
    try:
        dl_link = r.json().get("link")
    except Exception:
        print("Failed to parse download response JSON.")
        print("Status Code:", r.status_code)
        print("Response text:", r.text)
        return False

    if not dl_link:
        print("No download link found")
        return False

    # Downloads subtitle file
    sub_response = requests.get(dl_link, timeout=30)
    os.makedirs(save_path, exist_ok=True)
    srt_path = os.path.join(save_path, "subtitles.srt")
    with open(srt_path, "wb") as f:
        f.write(sub_response.content)

    print(f"Subtitle saved to: {srt_path}")

    # Converts to .vtt
    vtt_path = convert_srt_to_vtt(srt_path)
    return vtt_path is not None



# move biggest file from child to parent folder, renames file to 'movie.{ext}', removes child folder
def finalize_movie_folder(base_path):
    contents = os.listdir(base_path)
    dirs = [d for d in contents if os.path.isdir(os.path.join(base_path, d))]

    if len(dirs) != 1:
        current_app.logger.warning(f"Unexpected folder structure in {base_path}: {dirs}")
        return False

    inner_folder = os.path.join(base_path, dirs[0])
    video_files = []

    # finds biggest video file in child folder
    for root, _, files in os.walk(inner_folder):
        for file in files:
            if file.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
                full_path = os.path.join(root, file)
                size = os.path.getsize(full_path)
                video_files.append((size, full_path, file))

    if not video_files:
        current_app.logger.warning(f"No video files found in {inner_folder}")
        return False

    # Pick the largest video file
    _, src_path, original_filename = max(video_files, key=lambda x: x[0])
    ext = os.path.splitext(original_filename)[1]
    dst_path = os.path.join(base_path, f"movie{ext}")

    # move video file from child, then remove child
    shutil.move(src_path, dst_path)
    shutil.rmtree(inner_folder)
    current_app.logger.info(f"Moved {original_filename} to {dst_path} and removed {inner_folder}")
    return True



# downloads poster from tmdb database, given the movie id, and saves to given path
def download_poster_and_metadata(tmdb_id, save_path):
    
    # sends request to tmdb of given movie id
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}"}
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
    r = requests.get(url, headers=headers, timeout=10)
    
    if r.status_code != 200:
        current_app.logger.error(f"Failed to fetch TMDb data: {r.text}")
        return False

    data = r.json()
    poster_path = data.get("poster_path")

    # saves metadata of movie
    metadata = {
        "title": data.get("title"),
        "overview": data.get("overview"),
        "release_date": data.get("release_date"),
        "genres": [genre["name"] for genre in data.get("genres", [])],
        "runtime": data.get("runtime"),
        "rating": data.get("vote_average"),
        "poster_path": poster_path,
        "tmdb_id": tmdb_id
    }

    # places metadata and poster in the correct movie path
    metadata_file_path = os.path.join(save_path, "metadata.json")
    try:
        with open(metadata_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
    except Exception as e:
        current_app.logger.error(f"Failed to write metadata.json: {e}")
        return False

    if not poster_path:
        current_app.logger.warning(f"No poster path for TMDb ID {tmdb_id}")
        return False

    full_poster_url = f"https://image.tmdb.org/t/p/original{poster_path}"
    poster_response = requests.get(full_poster_url, stream=True, timeout=30)
    
    if poster_response.status_code == 200:
        poster_file = os.path.join(save_path, "poster.jpg")
        with open(poster_file, "wb") as f:
            for chunk in poster_response.iter_content(1024):
                f.write(chunk)
        return True

    current_app.logger.error(f"Failed to download poster image: {poster_response.status_code}")
    return False
