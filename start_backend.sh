#!/bin/bash
# Start the backend server using the virtual environment

cd "$(dirname "$0")"
source .venv/bin/activate
cd backend
python app.py

