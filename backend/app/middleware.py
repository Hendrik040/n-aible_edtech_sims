from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def configure_middleware(app: FastAPI):
    """
    Configure global API middleware.
    Includes CORS, error handling, etc.
    """
    
    # CORS Configuration
    # In a real app, these should come from settings
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:3000",      # IPv6 Localhost
        "http://[::1]:8000",      # IPv6 Localhost
        "*"                       # Fallback
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )
