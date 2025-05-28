# Flask PDF Manager - Production Deployment Guide (Windows + Nginx)

This guide explains how to deploy your Flask PDF Manager app in production on a clean Windows installation using Nginx as a reverse proxy.

## Prerequisites
- Windows 10/11 (clean install)
- Administrator privileges
- Internet connection

## 1. Install Python
- Download Python 3.10+ from [python.org](https://www.python.org/downloads/windows/)
- During installation, check **Add Python to PATH**

## 2. Install Git (optional, for code management)
- Download from [git-scm.com](https://git-scm.com/download/win)

## 3. Clone or Copy Your Project
- Place your project folder (e.g., `some_flask`) in your desired directory, e.g., `C:\apps\some_flask`

## 4. Create a Virtual Environment
Open PowerShell and run:
```powershell
cd C:\apps\some_flask
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## 5. Install Python Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Install and Configure Gunicorn (via Waitress for Windows)
Gunicorn is not available on Windows. Use [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/) instead:
```powershell
pip install waitress
```

## 7. Test the App with Waitress
```powershell
python -m waitress --listen=127.0.0.1:8000 app:app
```
- Visit [http://127.0.0.1:8000](http://127.0.0.1:8000) to verify the app is running.

## 8. Install Nginx for Windows
- Download the latest stable Nginx for Windows from [nginx.org](https://nginx.org/en/download.html)
- Extract to `C:\nginx`

## 9. Configure Nginx as a Reverse Proxy
Edit `C:\nginx\conf\nginx.conf` and add this server block inside `http { ... }`:
```nginx
server {
    listen       80;
    server_name  localhost;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias C:/apps/some_flask/static/;
    }
    location /uploads/ {
        alias C:/apps/some_flask/uploads/;
    }
}
```
- Adjust paths if your project is in a different location.

## 10. Start Nginx
Open PowerShell as Administrator:
```powershell
cd C:\nginx
start nginx.exe
```
- Visit [http://localhost](http://localhost) to access your app via Nginx.

## 11. Run Waitress as a Background Service (Optional)
For production, use [NSSM](https://nssm.cc/) or Windows Task Scheduler to run Waitress as a service:
```powershell
nssm install flask-app "C:\apps\some_flask\venv\Scripts\python.exe" "-m" "waitress" "--listen=127.0.0.1:8000" "app:app"
```

## 12. Security & Final Steps
- Change `app.secret_key` in `app.py` to a strong, random value.
- Set proper permissions on `uploads/` and database files.
- Use HTTPS in production (see Nginx SSL guides).
- Regularly back up your database and uploads.

---

**Your Flask PDF Manager is now running in production behind Nginx on Windows!**
