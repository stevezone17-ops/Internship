import os
os.environ["USE_MOCK_DB"] = "1"
from app import create_app
app = create_app()
app.run(host="127.0.0.1", port=5000, debug=False)
