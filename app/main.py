from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import reddit

app = FastAPI(
    title="Reddit Interaction API",
    description="Programmatic Reddit interaction through UI scraping with Playwright",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reddit.router, prefix="/api", tags=["reddit"])


@app.get("/")
async def root():
    return {"message": "Reddit Interaction API", "docs": "/docs"}
