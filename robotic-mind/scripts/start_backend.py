import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "robotic_mind.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        ws_max_size=1_000_000,
    )
