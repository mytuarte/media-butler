class ServiceRegistry:
    def __init__(self):
        self.discord = None
        self.notification = None
        self.overseerr = None
        self.radarr = None
        self.sonarr = None
        self.sonarr_search = None


services = ServiceRegistry()