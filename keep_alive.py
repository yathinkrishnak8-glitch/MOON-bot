from flask import Flask
from threading import Thread

# Initialize the Flask app
app = Flask('')

@app.route('/')
def home():
    # This is the message seen if someone visits the web URL
    return "HabibiBot Engine: ONLINE 🟢"

def run():
    # We use 0.0.0.0 to make it accessible to the external pinger
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """
    Starts the web server on a separate thread so it doesn't 
    block the main Discord bot from running.
    """
    t = Thread(target=run)
    t.start()
