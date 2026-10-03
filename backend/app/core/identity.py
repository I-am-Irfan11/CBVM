from contextvars import ContextVar

# Propagated through async request tasks and Starlette's thread pool.
actor = ContextVar("audit_actor", default={"user_id": "system:capture", "role": "system"})
