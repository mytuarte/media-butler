class ServiceRegistry:
    def __init__(self):
        self.discord = None
        self.notification = None
        self.overseerr = None
        self.radarr = None
        self.sonarr = None
        self.sonarr_search = None

        self.pipeline_monitor = None

        self.delete_confirmation = None
        self.delete = None

        self.search_channel = None

        self.health_monitor = None
        self.trending_movies = None


services = ServiceRegistry()
