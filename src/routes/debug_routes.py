import asyncio
import json
from datetime import datetime

from flask import Blueprint, jsonify

from models.health_issue import HealthIssue
from services.scenario_service import ScenarioService
from views.health_alert_view import HealthAlertView
from views.movie_details_view import MovieDetailsView

debug_routes = Blueprint(
    "debug_routes",
    __name__,
)


def initialize(
    discord_service,
    notification_service,
    overseerr_service,
    sonarr_search_service,
    sonarr_service,
    radarr_service,
):
    @debug_routes.get("/debug/sonarr")
    def debug_sonarr():
        sonarr_search_service.search("")

        return "Printed first Sonarr series to console."

    @debug_routes.get("/debug/sonarr/<title>")
    def debug_sonarr_title(title):
        sonarr_service.debug_series(title)

        return jsonify(
            {
                "message": "Series printed to console.",
            }
        )

    @debug_routes.get("/debug/sonarr/episode-files/<int:series_id>")
    def debug_episode_files(series_id):
        files = sonarr_service.get_episode_files(series_id)

        if not files:
            print("No episode files found.")

            return jsonify(
                {
                    "message": "No episode files found.",
                }
            )

        print(json.dumps(files[0], indent=4))

        return jsonify(
            {
                "count": len(files),
                "message": "First episode file printed to console.",
            }
        )

    @debug_routes.get("/debug/radarr/<title>")
    def debug_radarr(title):
        radarr_service.debug_movie(title)

        return jsonify(
            {
                "message": "Movie printed to console.",
            }
        )

    @debug_routes.get("/debug/overseerr/test")
    def overseerr_test():
        return jsonify(overseerr_service.test_connection())

    @debug_routes.get("/debug/overseerr/requests")
    def overseerr_requests():
        return jsonify(overseerr_service.get_requests())

    @debug_routes.get("/debug/overseerr/request/<int:tmdb_id>")
    def overseerr_request(tmdb_id):
        return jsonify(overseerr_service.get_request(tmdb_id))

    @debug_routes.get("/debug/overseerr/request/<int:tmdb_id>/dump")
    def overseerr_request_dump(tmdb_id):
        request = overseerr_service.debug_request(tmdb_id)

        if request is None:
            return (
                jsonify(
                    {
                        "error": "Request not found",
                    }
                ),
                404,
            )

        return jsonify(
            {
                "message": "Request printed to console.",
            }
        )

    @debug_routes.get("/debug/test")
    def test():
        future = asyncio.run_coroutine_threadsafe(
            notification_service.send_test_notification(),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        return "Test notification sent!"

    @debug_routes.get("/debug/test-health-alert")
    def test_health_alert():
        issue = HealthIssue(
            title="Test Health Alert",
            issue_type="test",
            details=(
                "This is a test health alert.\n"
                "The Discord health alert pipeline is working."
            ),
            created_at=datetime.now(),
            severity="warning",
        )

        embed = HealthAlertView.build(issue)

        future = asyncio.run_coroutine_threadsafe(
            discord_service.send_health_alert(embed),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        return "Health alert test sent."

    @debug_routes.get("/debug/scenario/released-not-downloaded")
    def released_not_downloaded():
        result = ScenarioService.released_not_downloaded()

        embed = MovieDetailsView.build(result)

        future = asyncio.run_coroutine_threadsafe(
            discord_service.send_embed(embed),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        return "Scenario sent."
