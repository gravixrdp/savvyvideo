#!/bin/bash
# Script to stop the bot service

echo "🛑 Stopping VideoSavvy Bot..."

sudo systemctl stop savvybot.service

echo "✅ Bot stopped!"

