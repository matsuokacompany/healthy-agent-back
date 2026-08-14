from fastapi.routing import APIRoute

from app.core.auth import get_current_super_admin
from app.routes.bot_webhook_routes import router


def test_debug_send_prompt_requires_super_admin_authentication():
    route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/debug/send-prompt"
    )

    dependencies = {dependency.call for dependency in route.dependant.dependencies}

    assert get_current_super_admin in dependencies
