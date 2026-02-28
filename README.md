# Amonogawa Stremio Addon (Python)

Stremio addon that serves Ukrainian-dubbed anime from [amanogawa.space](https://amanogawa.space). Browse the catalog, search by name (Ukrainian / English / Japanese), and stream episodes directly in Stremio via Telegram proxy.

## Features

- Anime catalog with pagination (series + movies)
- Search across all titles (client-side, UA + EN/JP names)
- Full metadata: poster, background, genres, director, episode list
- Season / part disambiguation in titles
- Video streaming from Telegram via Pyrogram
- HTTP Range support (seeking works)
- Toloka torrent links as fallback

## Tech Stack

- **Python 3.12** + **FastAPI** + **uvicorn**
- **httpx** (async HTTP client)
- **Pyrogram** for Telegram MTProto streaming

## Setup

### 1. Clone and install

```bash
git clone git@github.com:voogryk/amonogawa-stremio-py.git
cd amonogawa-stremio-py
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx pyrogram tgcrypto python-dotenv
```

> `tgcrypto` is optional but recommended — speeds up Pyrogram's encryption significantly.

### 2. Get Telegram API credentials

Go to [my.telegram.org](https://my.telegram.org/apps), sign in, and create an app. You'll get an `api_id` and `api_hash`.

### 3. Create `.env`

```
TG_API_ID=12345678
TG_API_HASH=your_api_hash_here
```

### 4. Authenticate with Telegram

This is a **one-time step**. It logs into your Telegram account and saves a session file (`amonogawa.session`) so the server can stream videos on your behalf.

```bash
python auth.py
```

You'll be prompted for:
1. Your phone number (with country code, e.g. `+380...`)
2. The login code Telegram sends you
3. 2FA password (if you have one set up)

After success, you'll see:
```
Authorized as: YourName (@yourusername)
Session file created. You can now run the server.
```

> **Important:** `amonogawa.session` contains your Telegram session. Never commit it or share it. It's already in `.gitignore`.

### 5. Start the server

```bash
uvicorn main:app --host 0.0.0.0 --port 7000
```

Or via Python directly:

```bash
python main.py
```

You should set `BASE_URL` to the public URL where the server is reachable (needed for Telegram streaming links):

```bash
BASE_URL=http://your-server-ip:7000 uvicorn main:app --host 0.0.0.0 --port 7000
```

### 6. Add to Stremio

Open Stremio and go to the addon catalog. Add by URL:

```
http://your-server-ip:7000/manifest.json
```

Or on the same machine:

```
http://localhost:7000/manifest.json
```

## Hosting

### Local network (home use)

Run the server on your PC/laptop and connect from any device on the same Wi-Fi (phone, TV, tablet).

1. Find your local IP:
   ```bash
   # macOS
   ipconfig getifaddr en0

   # Linux
   hostname -I | awk '{print $1}'

   # Windows (look for "IPv4 Address")
   ipconfig
   ```

2. Start with your local IP as `BASE_URL`:
   ```bash
   BASE_URL=http://192.168.1.42:7000 uvicorn main:app --host 0.0.0.0 --port 7000
   ```

3. In Stremio on any device in the same network, add the addon:
   ```
   http://192.168.1.42:7000/manifest.json
   ```

> **Note:** `BASE_URL` must be your local IP, not `localhost` — otherwise streaming links won't work from other devices. Your local IP may change over time; you can fix it in your router settings (DHCP reservation).

### VPS

#### Quick start (nohup)

The simplest way — just run in the background and disconnect:

```bash
BASE_URL=http://your-server-ip:7000 nohup uvicorn main:app --host 0.0.0.0 --port 7000 > server.log 2>&1 &
```

Check logs: `tail -f server.log`. Stop: `kill $(pgrep -f uvicorn)`.

#### systemd

Create `/etc/systemd/system/amonogawa.service`:

```ini
[Unit]
Description=Amonogawa Stremio Addon
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/amonogawa-stremio-py
Environment=BASE_URL=http://your-server-ip:7000
ExecStart=/path/to/amonogawa-stremio-py/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 7000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable amonogawa
sudo systemctl start amonogawa
```

Check logs:
```bash
journalctl -u amonogawa -f
```

#### Docker (optional)

Create a `Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
```

Create `requirements.txt`:

```
fastapi
uvicorn
httpx
pyrogram
tgcrypto
python-dotenv
```

```bash
docker build -t amonogawa .
docker run -d \
  --name amonogawa \
  -p 7000:7000 \
  -e BASE_URL=http://your-server-ip:7000 \
  -v $(pwd)/.env:/app/.env:ro \
  -v $(pwd)/amonogawa.session:/app/amonogawa.session:ro \
  --restart unless-stopped \
  amonogawa
```

#### Firewall

Make sure port `7000` (or whichever you chose) is open:

```bash
sudo ufw allow 7000/tcp
```

## Project Structure

```
amonogawa_client.py  — Amonogawa API client with TTL cache
stremio.py           — Stremio protocol response builders
telegram_stream.py   — Telegram streaming bridge (Pyrogram)
main.py              — FastAPI server, all endpoints
auth.py              — One-time Telegram auth script
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /manifest.json` | Stremio manifest |
| `GET /catalog/:type/:id.json` | Catalog page |
| `GET /catalog/:type/:id/skip=:n.json` | Catalog with pagination |
| `GET /catalog/:type/:id/search=:q.json` | Search by name |
| `GET /meta/:type/:id.json` | Title metadata + episodes |
| `GET /stream/:type/:id.json` | Stream sources |
| `GET /tg/stream/:botId` | Telegram video proxy |
