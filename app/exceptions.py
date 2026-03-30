class AppError(Exception):
    status_code = 400
    flash_category = "error"

    def __init__(self, message, *, status_code=None, flash_category=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if flash_category is not None:
            self.flash_category = flash_category


class ValidationError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404
    flash_category = "warning"


class PermissionDeniedError(AppError):
    status_code = 403


class BusinessRuleError(AppError):
    status_code = 409


class TenantIsolationError(PermissionDeniedError):
    pass


class SubscriptionRequiredError(AppError):
    status_code = 402
