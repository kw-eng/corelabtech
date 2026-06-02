from flask import Flask


def configure_security_headers(app: Flask):

    @app.after_request
    def apply_security_headers(response):

        # =====================================================
        # MIME sniffing protection
        # =====================================================

        response.headers["X-Content-Type-Options"] = "nosniff"

        # =====================================================
        # Clickjacking protection
        # =====================================================

        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # =====================================================
        # Basic XSS protection
        # =====================================================

        response.headers["X-XSS-Protection"] = "1; mode=block"

        # =====================================================
        # Referrer policy
        # =====================================================

        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # =====================================================
        # Content Security Policy
        # =====================================================

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "font-src 'self' data:;"
        )

        # =====================================================
        # HTTPS Strict Transport Security
        # only enable in production HTTPS
        # =====================================================

        # response.headers["Strict-Transport-Security"] = (
        #     "max-age=31536000; includeSubDomains"
        # )

        return response