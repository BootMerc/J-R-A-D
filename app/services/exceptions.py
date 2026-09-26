class NotFoundError(Exception):
    # Raised by a service when a requested entity doesn't exist.
    #
    # The global FastAPI exception handler in app/main.py converts this into
    # a 404 response, so individual routers don't need to handle it themselves.
    pass
