#!/bin/bash
# Script to start the bot as a systemd service

echo "🚀 Setting up VideoSavvy Bot as a systemd service..."

# Copy service file to systemd directory
sudo cp /home/ubuntu/savvybot/savvybot.service /etc/systemd/system/

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable savvybot.service

# Start the service
sudo systemctl start savvybot.service

# Check status
echo ""
echo "✅ Bot service started!"
echo ""
echo "📊 Service Status:"
sudo systemctl status savvybot.service --no-pager -l

echo ""
echo "📝 Useful commands:"
echo "  Check status:  sudo systemctl status savvybot"
echo "  View logs:     sudo journalctl -u savvybot -f"
echo "  Stop bot:      sudo systemctl stop savvybot"
echo "  Restart bot:   sudo systemctl restart savvybot"
echo "  Start bot:     sudo systemctl start savvybot"

