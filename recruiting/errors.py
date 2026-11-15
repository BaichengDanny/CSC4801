"""Expected, user-visible business errors."""


class DomainError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message
