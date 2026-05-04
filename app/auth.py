import requests
from flask import request, abort, session

def identify_user():
    if request.path.startswith("/media_library") or request.path.startswith("/static"):
        return
    
    user_email = request.headers.get("Cf-Access-Authenticated-User-Email")
    if not user_email:
        abort(403)
    
    request.user_email = user_email

    # Only fetch from Cloudflare once per session
    if "user_name" not in session:
        session["user_name"] = get_user_name(request)
    
    request.user_name = session["user_name"]

    from .state import record_user
    record_user(user_email, request.user_name)


def get_user_name(request):
    try:
        # cloudflare access identity endpoint returns full profile
        cf_cookie = request.cookies.get("CF_Authorization")
        response = requests.get(
            "https://manavdodia.cloudflareaccess.com/cdn-cgi/access/get-identity",
            headers={"Cookie": f"CF_Authorization={cf_cookie}"},
            timeout=5,
        )
        if response.status_code == 200:
            identity = response.json()
            name = identity.get("name")  # e.g. "Manav Dodia"
            if name:
                return name.split()[0]  # just first name -> "Manav"
    except Exception:
        pass
    
    # fallback to email username
    return request.headers.get("Cf-Access-Authenticated-User-Email", "").split('@')[0]
