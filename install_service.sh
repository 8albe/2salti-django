#!/bin/bash
echo "🚀 Installing Service..."
echo "***REMOVED***" | sudo -S cp /home/alberto/formichina.service /etc/systemd/system/
echo "***REMOVED***" | sudo -S cp /home/alberto/nginx_config /etc/nginx/sites-available/formichina
echo "***REMOVED***" | sudo -S ln -sf /etc/nginx/sites-available/formichina /etc/nginx/sites-enabled/

echo "🔄 Reloading Systemd..."
echo "***REMOVED***" | sudo -S systemctl daemon-reload
echo "***REMOVED***" | sudo -S systemctl enable formichina
echo "***REMOVED***" | sudo -S systemctl restart formichina

echo "🌐 Restarting Nginx..."
echo "***REMOVED***" | sudo -S systemctl restart nginx

echo "✅ Done!"
