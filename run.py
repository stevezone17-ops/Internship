import os

# Use real MongoDB by default so data is visible in MongoDB Compass.
# Set USE_MOCK_DB=1 only when explicitly testing with mongomock.
os.environ.setdefault("USE_MOCK_DB", "0")
from app import create_app
app = create_app()
app.run(host="127.0.0.1", port=5000, debug=False)
