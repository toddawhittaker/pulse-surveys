"""HTTP routers (SPEC §13).

Routers stay thin: they read the request, call a service, and return a schema.
Domain logic belongs in `app/services/`, behind the authorization chokepoint.
"""
