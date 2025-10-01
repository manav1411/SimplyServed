# SimplyServed - a Media Streaming Server
**Privacy-first, multi-user, self-hosted streaming platform with automated torrent downloads, and real-time progress tracking.**  
live demo: [home.manavdodia.com](https://home.manavdodia.com). Please contact me on [Linkedin](https://www.linkedin.com/in/manav-dodia/) if you would like access for a demo.


## Desktop Demo

https://github.com/user-attachments/assets/300dace1-8348-46d3-9c9b-a4cc17651930

<details>
<summary>More demos</summary>

### Desktop Screenshots
<img width="1440" height="900" alt="mac screenshot 1" src="https://github.com/user-attachments/assets/a4ad54f0-8d10-4d6a-a4fd-eb3c7b7ebbb1" />
<img width="1440" height="900" alt="mac screenshot 2" src="https://github.com/user-attachments/assets/9fe0beaf-abb3-4343-be42-4f612116b68d" />


### Mobile Demo

https://github.com/user-attachments/assets/9a0b5a3c-fd86-4828-afd7-acf520f5a459

### Mobile Screenshots
<img width="402" height="874" alt="iphone screenshot 1" src="https://github.com/user-attachments/assets/d39f172b-56df-4588-be37-a22e810ed201" />
<img width="402" height="874" alt="iphone screenshot 2" src="https://github.com/user-attachments/assets/ab776e3c-7f46-43cf-b10f-0934e512a227" />
</details>


## Architecture Component Diagram
<img width="3840" height="2509" alt="architecture" src="https://github.com/user-attachments/assets/5e9613a4-44af-45d1-8043-6ab657648b97" />


## Architecture Sequence Diagram
<img width="7680" height="3124" alt="sequence" src="https://github.com/user-attachments/assets/9d113577-1d7d-4ec1-b13d-d465e757ee4e" />


## Overview
SimplyServed is a self-hosted, privacy-focused media streaming platform built entirely from scratch (Unlike off-the-shelf platforms like Plex or Jellyfin) using Flask, NGINX, Jackett, and Cloudflare Access. It enables multiple authorized users to remotely search, request, and stream movies seamlessly—with automatic torrent downloading, metadata fetching, subtitle support, and personalised playback progress tracking. This project particularly demonstrates expertise in software architecture, backend engineering, networking, API ingegration, security engineering, and end-to-end software design.\
SimplyServed developed my hands-on experience across the full stack and infrastructure when implementing:
- Designing and securing a multi-user streaming service
- Integrating APIs for torrents (Jackett), metadata (TMDb), and subtitles (OpenSubtitles)
- Automating torrent downloads and managing media files and subtitles
- Real-time download and playback progress synchronization
- Optimizing media streaming with HTTP byte-range support via NGINX
- Implementing OAuth-based authentication with Cloudflare Access
- Deploying and managing systemd services on a Linux home server
- Building a responsive frontend with custom video controls


## How It Works - Example Flow 
- User signs in, and searches for a movie → Flask calls TMDb for poster and metadata.  
- Flask queries Jackett for torrent results, picks the best seeded.  
- qBittorrent starts downloading automatically, with progress tracked in real-time.  
- After download, media files (video, poster, subtitles) are saved and organized.  
- Users can stream the movie remotely with subtitles and resume where they left off.  
- Users can cancel requests to remove torrents and cleanup partial downloads, or similar from current media library.


## Tech Stack

| Layer              | Tech          | Purpose                              |
|--------------------|---------------------------|------------------------------------|
| Hardware           | Raspberry Pi 400 + SSD    | Self-hosted media server              |
| Backend Framework  | Python Flask              | Web server and API                    |
| Web Server         | NGINX                     | Reverse proxy and static/media hosting |
| Torrent Indexer    | Jackett                   | Torrent search aggregation            |
| Torrent Client     | qBittorrent-nox           | Headless torrent downloading and management          |
| Media Storage      | External SSD (Mounted)    | Storage for /media_library files      |
| Domain & DNS       | Cloudflare                | DNS management, secure tunneling      |
| Authentication     | Cloudflare Access + Google OAuth | Secure, email-based user authentication |
| External APIs      | TMDb (movie poster/metadata), OpenSubtitles (subtitle files), Jackett (torrent indexer aggregation) | Movie metadata/poster, subtitles, movie files |
| Media Processing   | ffmpeg                    | Subtitle conversion (SRT → VTT)     |
| Frontend           | HTML/CSS/JS               | Responsive UI and video player      |
| Communication      | APIs                      | Backend interaction with services   |


## Folder Structure:
```
/app
├── auth.py
├── __init__.py
├── /routes
│   ├── main.py
│   ├── media.py
│   ├── progress.py
├── /static
│   ├── global.css
│   └── movie.css
├── /templates
│   ├── index.html
│   └── movie.html
├── user_progress.json
└── utils.py
/media_library
  └── Movie_Name/
       ├── movie.mp4
       ├── subtitles.vtt
       ├── metadata.json
       └── poster.jpg
run.py
README.md
```
Media files are organized in /media_library, each movie in its own folder named after the movie, containing `movie.mp4`, `subtitles.vtt`, `metadata.json`, and `poster.jpg`.


## Security & Privacy  
- Access to the platform is strictly restricted via Cloudflare Access using Google OAuth, ensuring only authorized users can search, request, or stream content.
- No data is shared with third-party streaming services; all media is stored locally on your own hardware.  
- All sensitive API keys are stored in environment variables and never exposed to the frontend.


## Features
- Movie Search and Request -> Users can search for movies using the TMDb API from the homepage.
- Automated Torrent Download -> The most seeded torrent matching the search is automatically downloaded via Jackett + qBittorrent.
- Download Progress Tracking -> The UI shows real-time progress of torrent downloads per requested movie.
- Playback Progress Persistence -> Tracks where each user left off in a movie; resumes playback accordingly.
- Subtitles Support -> Automatically downloads and converts subtitles to .vtt for in-browser display.
- Multi-user Support -> Multiple users authenticated through Cloudflare Access share the media library but have separate playback states.
- Mobile-Friendly Interface -> Responsive design with custom video controls optimized for touch.
- Secure Access -> Restricts access to authorized users via Cloudflare Access.


## Future Improvements - Contributions are welcome
- Add TV show and episodic content support (to support series and binge-watching).
- Implement HLS adaptive streaming for better performance on slower networks.
- Include extra metadata like trailers, cast info, and reviews to enrich the user experience.
- Support other file formats (e.g., mkv) to increase media compatibility.
- Improve subtitles accuracy by enabling user-selectable options and timing offsets.
- Add a user management UI to streamline access without Cloudflare email whitelist edits.
- Enable searching/filtering within the media library for scalability.
- Change requested movies from being session based to something more bulletproof (JSON?)
- Sort movies by amount watched + alphabetically within


## Key Files & Components
- server.py: Flask backend handling requests and user sessions
- nginx.conf: Reverse proxy configuration, byte-range support
- jackett.service: Background torrent indexer
- qbittorrent-nox.service: Background torrent client
- /media_library/: Organized media folder
- metadata.json: Stores movie metadata retrieved from TMDb
- .env: Environment variables including API keys


## Setup and Running
I do not expect many people to actually run this, it is more so a demonstration of my skills. Nevertheless, if you are so inclined, the steps are below.

### Prerequisites:
- Knowledge (or willingness to learn!): intermediate Linux skills, Python Flask, NGINX reverse proxy, torrent clients, and API key management.
- Linux server (e.g. Raspberry Pi) with Python 3.x
- Flask app and dependencies (see Python files)
- NGINX configured as reverse proxy
- Jackett, qBittorrent-nox with APIs set up
- OpenSubtitles, TMdb API keys
- Cloudflared tunnel configured with your domain
- (Optional) Docker for containerized deployment

### Starting Services
```
sudo systemctl restart server           # Flask server on port 8000 (dev alt to gunicorn->) # alt: python3 run.py
sudo systemctl restart server_gunicorn   # Gunicorn server on port 8000 (prod alt to flask^) # alt: 'gunicorn --bind 0.0.0.0:8000 "app:create_app()"'
sudo systemctl restart cloudflared      # Cloudflare tunnel
sudo systemctl restart nginx            # NGINX reverse proxy on port 5000
sudo systemctl restart jackett          # Torrent indexer on port 9117
sudo systemctl restart qbittorrent-nox  # Torrent client on port 8080
```
Modify the .env.example file to modify env variables. `SSH`-ing into your server is recomended.

### Usage
- Visit https://home.yourdomain.com
- Log in via Cloudflare Access
- Search or request movies from the homepage
- Click a poster to stream with subtitles and resume playback support
- Track download and playback progress in real time
