from flask import Blueprint, jsonify

system_routes = Blueprint(
    "system_routes",
    __name__,
)


@system_routes.get("/")
def home():
    return "Media Butler is running!"


@system_routes.get("/health")
def health():
    return jsonify(
        {
            "status": "healthy",
            "version": "0.2.0",
        }
    )