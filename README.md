# ClipGrab
- A fast and simple video clipper for YouTube, X, Instagram, and more.
- Just paste a link, optionally select a start and end time, and download the exact clip you need.
- The Chrome extension auto-detects videos from your current tab to make clipping even faster.

<video src="https://github.com/user-attachments/assets/6212ee20-2571-4ea4-bcfe-077f26aba9e2" width="100%" controls></video>

## Supported Platforms

- **X / Twitter**
- **Instagram**
- **Reddit**
- **Vimeo**
- **Twitch** (clips)
- **Streamable**

## How It Works

1. You paste a video URL on the website.
2. The Python backend uses **yt-dlp** to extract the direct stream URL.
3. **FFmpeg** (via `imageio-ffmpeg`) slices the requested time range.
4. The clipped video is streamed back to your browser as a download.

## System Architecture

```mermaid
graph TD
    %% User Interfaces
    subgraph Client ["Client Side (User Interfaces)"]
        Web["Web Frontend (index.html, styles.css, app.js)"]
        Ext["Chrome Extension (popup.html, popup.js)"]
    end

    %% Vercel Platform
    subgraph Vercel ["Vercel Hosting Platform"]
        Router["Vercel Edge Router (vercel.json)"]
        
        subgraph Static ["Static Hosting"]
            Front["frontend/ folder"]
        end
        
        subgraph Serverless ["Serverless Functions"]
            Flask["Flask Application (api/index.py)"]
        end
    end

    %% Backend Libraries
    subgraph Backend_Tools ["Backend Processing Engines"]
        YTDL["yt-dlp (Stream Extractor)"]
        FFMPEG["FFmpeg (imageio-ffmpeg Slicer)"]
    end

    %% External Sources
    subgraph External ["External Video Sources"]
        Twitter["X / Twitter"]
        Insta["Instagram"]
        Reddit["Reddit"]
        Vimeo["Vimeo"]
        Twitch["Twitch (Clips)"]
        Streamable["Streamable"]
    end

    %% Connections - Routing
    Web -->|"Static HTTP Request"| Router
    Ext -->|"POST /clip (URL + Timestamps)"| Router
    Router -->|"1. Rewrite /* to frontend/"| Front
    Router -->|"2. Route /clip to api/index.py"| Flask

    %% Connections - Backend Processing
    Flask -->|"3. Query Stream URL"| YTDL
    YTDL -->|"4. Request Video Info"| External
    External -->|"5. Return Stream URL Metadata"| YTDL
    YTDL -->|"6. Return Direct Stream URL"| Flask
    
    Flask -->|"7. Slice Selected Range"| FFMPEG
    FFMPEG -->|"8. Seek & Stream Video Segments"| External
    External -->|"9. Video Stream Bytes"| FFMPEG
    FFMPEG -->|"10. Write Temporary Output File"| Flask
    
    Flask -->|"11. Send MP4 Stream (as_attachment)"| Router
    Router -->|"12. Trigger Local File Download"| Client
    
    %% Styling
    classDef client fill:#1f1f1f,stroke:#83ee87,stroke-width:2px,color:#fff;
    classDef vercel fill:#000,stroke:#555,stroke-width:2px,color:#fff;
    classDef tools fill:#2d2e30,stroke:#3c4043,stroke-width:1px,color:#fff;
    classDef external fill:#151515,stroke:#444,stroke-dasharray: 5 5,color:#fff;
    
    class Web,Ext client;
    class Router,Front,Flask vercel;
    class YTDL,FFMPEG tools;
    class Twitter,Insta,Reddit,Vimeo,Twitch,Streamable external;
```

## Run Locally

```bash
git clone https://github.com/Arav-Arun/ClipGrab.git
cd ClipGrab
pip3 install -r requirements.txt
python3 api/index.py
```

Open `http://localhost:9000`.

## Chrome Extension

The extension auto-detects video URLs from your current tab for one-click clipping.

**To install locally:**

1. Go to `chrome://extensions/`.
2. Enable **Developer mode** (top-right).
3. Click **Load unpacked** → select the `frontend/extension/` folder.
4. Pin it to your toolbar.
