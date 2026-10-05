"""Domain exceptions raised by the P.W Auto Service service layer."""


class ServiceError(Exception):
    """Base class for expected service-layer errors."""


class NotFoundError(ServiceError):
    """Raised when a requested domain record does not exist."""


class ValidationError(ServiceError):
    """Raised when supplied data violates a business rule."""


class InvalidStatusTransition(ServiceError):
    """Raised when a job-card status transition is not allowed."""


class InsufficientStockError(ServiceError):
    """Raised when an inventory operation would make stock negative."""
