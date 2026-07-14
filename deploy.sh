#!/bin/bash

set -e

echo "========================================"
echo " Media Butler Deployment"
echo "========================================"

cd "$(dirname "$0")"

echo
echo "Using project SSH configuration..."
export GIT_SSH_COMMAND="ssh -F $(pwd)/.ssh/config"

echo
echo "Pulling latest code..."
git pull origin feature/discord-commands

echo
echo "Stopping existing container..."
sudo docker compose -f docker.compose.yaml down

echo
echo "Building image..."
sudo docker compose -f docker.compose.yaml build

echo
echo "Starting container..."
sudo docker compose -f docker.compose.yaml up -d

echo
echo "Running containers:"
sudo docker ps | grep media-butler

echo
echo "Recent logs:"
sudo docker logs --tail 20 media-butler

echo
echo "========================================"
echo " Deployment Complete"
echo "========================================"