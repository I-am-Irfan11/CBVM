from fastapi import Request


def operations(request: Request):
    return request.app.state.operations
