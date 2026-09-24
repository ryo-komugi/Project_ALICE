from fastapi import FastAPI, Request

app = FastAPI()


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "ALICE_LineTest is running."
    }


@app.post("/callback")
async def callback(request: Request):
    body = await request.body()

    print("=" * 60)
    print("Webhook received!")
    print(body.decode("utf-8"))
    print("=" * 60)

    return {"status": "received"}