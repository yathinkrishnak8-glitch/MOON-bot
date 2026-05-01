from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "habbibi mod (: is online and ready to troll on Render."

def run():
    # Render assigns a random port, this grabs it dynamically!
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
