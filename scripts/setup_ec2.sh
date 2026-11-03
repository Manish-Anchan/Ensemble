#!/usr/bin/env bash
# ==============================================================================
# ENSEMBLE: AWS EC2 One-Command Setup Script
# Works on: Deep Learning OSS Nvidia Driver AMI GPU (Ubuntu 22.04 / 24.04)
# ==============================================================================
set -euo pipefail

echo "======================================================================"
echo "🎭 Ensemble Audio Drama Studio: AWS EC2 Deployment Setup"
echo "======================================================================"

# 1. Verify NVIDIA GPU
if command -v nvidia-smi &> /dev/null; then
    echo "⚡ NVIDIA GPU Detected:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "⚠️  No NVIDIA driver detected via nvidia-smi. Kokoro will fall back to tuned CPU."
fi

# 2. Install astral-sh uv if not already present
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# 3. Install system dependencies (soundfile / libsndfile1)
echo "📦 Ensuring system audio libraries are installed..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y libsndfile1 ffmpeg curl wget

# 4. Sync Python dependencies via uv
echo "📦 Installing Python environment and packages..."
uv sync

# 5. Download Kokoro Neural Voice Models
echo "📥 Checking Kokoro-82M ONNX Model and Voice Pack..."
mkdir -p models

if [ ! -f "models/kokoro-v1.0.onnx" ]; then
    echo "  Downloading kokoro-v1.0.onnx (325MB)..."
    curl -L "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" -o models/kokoro-v1.0.onnx
else
    echo "  ✓ kokoro-v1.0.onnx already exists."
fi

if [ ! -f "models/voices-v1.0.bin" ]; then
    echo "  Downloading voices-v1.0.bin (28MB)..."
    curl -L "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" -o models/voices-v1.0.bin
else
    echo "  ✓ voices-v1.0.bin already exists."
fi

# 6. Ensure .env file exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "📝 Created .env from .env.example. Remember to add your Gemini (DIRECTOR_API_KEY) and Groq (PRODUCER_API_KEY) keys!"
    else
        touch .env
    fi
fi

# 7. Auto-configure systemd service paths for this instance
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)
sed -i "s|/home/ubuntu/Ensemble|$CURRENT_DIR|g" scripts/ensemble.service
sed -i "s|User=ubuntu|User=$CURRENT_USER|g" scripts/ensemble.service

# 8. Run backend test suite to verify installation
echo "🧪 Running unit tests..."
.venv/bin/pytest -q

echo "======================================================================"
echo "✅ Ensemble is ready on AWS!"
echo "Next Steps:"
echo "  1. Add your API keys to .env (nano .env)"
echo "  2. Start the Web Studio interactively:"
echo "       uv run python -m ensemble.web --port 8080"
echo "     Or run 24/7 as a background service:"
echo "       sudo cp scripts/ensemble.service /etc/systemd/system/"
echo "       sudo systemctl daemon-reload"
echo "       sudo systemctl enable --now ensemble"
echo "======================================================================"
