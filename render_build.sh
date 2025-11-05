#!/usr/bin/env bash
# Render build script for video stitching API

set -o errexit

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing FFmpeg..."
apt-get update
apt-get install -y ffmpeg

echo "Verifying FFmpeg installation..."
ffmpeg -version

echo "Build completed successfully!"