class AgentError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class BusyLearningError(RuntimeError):
    """Raised when a send is attempted while a learn session is active."""
