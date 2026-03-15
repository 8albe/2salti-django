#!/bin/bash

echo "🚀 Starting Django Deployment..."

# 1. Install Gunicorn
echo "📦 Installing Gunicorn..."
source .venv/bin/activate
pip install gunicorn

# 2. Collect Static Files
echo "🎨 Collecting Static Files..."
python manage.py collectstatic --noinput

# 3. Setup Systemd Service
echo "⚙️ Configuring Systemd Service..."
sudo tee /etc/systemd/system/formichina.service > /dev/null <<EOT
[Unit]
Description=gunicorn daemon for formichina
After=network.target

[Service]
User=alberto
Group=www-data
WorkingDirectory=/home/alberto
ExecStart=/home/alberto/.venv/bin/gunicorn --access-logfile - --workers 3 --bind unix:/tmp/formichina.sock config.wsgi:application

[Install]
WantedBy=multi-user.target
EOT

# 4. Setup Nginx
echo "🌐 Configuring Nginx..."
sudo cp /home/alberto/nginx_config /etc/nginx/sites-available/formichina
sudo ln -sf /etc/nginx/sites-available/formichina /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 5. Restart Services
echo "🔄 Restarting Services..."
sudo systemctl daemon-reload
sudo systemctl start formichina
sudo systemctl enable formichina
sudo systemctl restart formichina
sudo systemctl restart nginx

echo "✅ Deployment Completed! Check http://formichina.com"
