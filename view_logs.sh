#!/bin/bash
# Script to view bot logs

echo "📋 Viewing VideoSavvy Bot logs (Press Ctrl+C to exit)..."
echo ""

sudo journalctl -u savvybot -f

