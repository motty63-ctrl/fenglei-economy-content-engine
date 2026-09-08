"""Domain errors with stable CLI exit codes."""


class FangleiError(Exception):
    exit_code = 1


class EmptyInputError(FangleiError):
    exit_code = 2


class InputPathError(FangleiError):
    exit_code = 3


class RunPathError(FangleiError):
    exit_code = 4


class ProviderError(FangleiError):
    exit_code = 5


class ArtifactConflictError(FangleiError):
    exit_code = 6
