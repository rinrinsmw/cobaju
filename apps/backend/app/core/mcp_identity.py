"""Private process identity used only between the backend and its MCP child."""

import os


# This variable is injected into one child process by trusted backend code. It
# must never be populated from HTTP input, MCP arguments, or the shared .env.
MCP_RUNTIME_USER_ID_ENV = "COBAJU_INTERNAL_MCP_USER_ID"


class McpRuntimeIdentityError(RuntimeError):
    """Raised when a child process has no valid trusted user identity."""


def get_mcp_runtime_user_id() -> int:
    """Read and strictly validate the backend-injected child-process identity."""

    raw_user_id = os.environ.get(MCP_RUNTIME_USER_ID_ENV)
    if raw_user_id is None:
        raise McpRuntimeIdentityError("MCP runtime user identity is missing")
    try:
        user_id = int(raw_user_id)
    except ValueError as error:
        raise McpRuntimeIdentityError("MCP runtime user identity is invalid") from error
    if user_id < 1:
        raise McpRuntimeIdentityError("MCP runtime user identity is invalid")
    return user_id
