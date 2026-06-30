import os

from flask import Flask, request
from dotenv import load_dotenv

load_dotenv("config/.env")

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "Media Butler is running."


@app.route("/radarr", methods=["POST"])
def radarr():
    data = request.json

    print("========== RADARR WEBHOOK ==========")
    print(data)
    print("====================================")

    return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)