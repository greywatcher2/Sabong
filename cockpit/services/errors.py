class DomainError(Exception):
    pass


class AuthError(DomainError):
    pass


class PermissionError(DomainError):
    pass


class ValidationError(DomainError):
    pass

