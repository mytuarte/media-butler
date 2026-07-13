from abc import ABC


class BaseView(ABC):
    """
    Base class for Discord presentation components.

    Views are responsible only for presentation.
    They should not perform API calls or contain
    business logic.
    """

    pass