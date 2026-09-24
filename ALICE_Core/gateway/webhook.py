from fastapi import APIRouter, Request, HTTPException
import logging
from config import CHANNEL_SECRET
from gateway.signature import SignatureVerifier
from gateway.dispatcher import EventDispatcher

router = APIRouter()
logger = logging.getLogger(__name__)

verifier = SignatureVerifier(CHANNEL_SECRET)
dispatcher = EventDispatcher()


@router.post("/callback")
async def callback(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    if signature is None:
        raise HTTPException(status_code=400, detail="Missing Signature")

    if not verifier.verify(body, signature):
        raise HTTPException(status_code=403, detail="Invalid Signature")

    logger.info("Signature OK")
    payload = await request.json()

    for event in payload.get("events", []):
        dispatcher.dispatch(event)

    logger.info("Request completed")
    return {"status": "ok"}
