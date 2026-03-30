# RC Lookup — rc.hirav.me

Full-stack vehicle registration lookup tool.
- **Frontend**: Static HTML/CSS/JS served via nginx
- **Backend**: Python FastAPI calling iDfy RC API + MCA21 director scraping
- **Proxy**: nginx reverse proxy routing `/api/*` → FastAPI, `/` → frontend

---

## Project Structure

```
rc-lookup/
├── backend/
│   ├── main.py           # FastAPI app + iDfy API call
│   ├── mca_scraper.py    # MCA21 scraper for director DIN lookup
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html        # Single-file frontend
│   ├── nginx-frontend.conf
│   └── Dockerfile
├── nginx/
│   ├── default.conf      # HTTP only (dev / first deploy)
│   └── default-ssl.conf  # HTTPS with SSL (production)
├── docker-compose.yml
└── .env.example
```

---

## Deployment on rc.hirav.me

### 1. Clone / upload to your server

```bash
scp -r rc-lookup/ user@your-server:~/rc-lookup
# or git clone your repo
```

### 2. Set credentials

```bash
cd ~/rc-lookup
cp .env.example .env
nano .env   # fill in IDFY_ACCOUNT_ID and IDFY_API_KEY
```

### 3. First deploy (HTTP only, to get SSL cert)

```bash
# Use the HTTP-only nginx config
cp nginx/default.conf nginx/active.conf

docker compose up -d --build
```

### 4. Get SSL certificate via Certbot

```bash
docker run --rm \
  -v $(pwd)/nginx/certs:/etc/letsencrypt \
  -v certbot_www:/var/www/certbot \
  certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    -d rc.hirav.me \
    --email you@email.com \
    --agree-tos \
    --non-interactive

# Copy certs to nginx/certs/
cp /etc/letsencrypt/live/rc.hirav.me/fullchain.pem nginx/certs/
cp /etc/letsencrypt/live/rc.hirav.me/privkey.pem nginx/certs/
```

### 5. Switch to SSL nginx config

```bash
cp nginx/default-ssl.conf nginx/default.conf
docker compose restart nginx
```

### 6. Verify

```bash
curl https://rc.hirav.me/health
# → {"status":"ok"}
```

---

## DNS

Point `rc.hirav.me` A record to your server IP before running certbot.

---

## How it works

1. User enters a registration number (e.g. `MH12AB1234`)
2. Frontend POSTs to `/api/lookup`
3. Backend calls iDfy `/verify_with_source/ind_rc_basic`
4. If owner name looks like a company (contains "pvt", "ltd", "llp", etc.):
   - Scrapes MCA21 portal to find directors + DIN numbers
   - Fetches each director's details (name, email, phone, address) from MCA
5. Full result returned and rendered in the UI

---

## Notes on MCA Scraping

- MCA21 occasionally rate-limits or changes its HTML structure
- Email/phone fields on MCA are often masked for privacy — the scraper will return what's publicly available
- If MCA returns no results, the app still shows the RC details and notes the company name with a manual lookup link

---

## Updating

```bash
cd ~/rc-lookup
git pull          # if using git
docker compose up -d --build
```
