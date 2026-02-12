"""多模态生成 API 路由"""

import base64

from fastapi import APIRouter, HTTPException

from state import state
from models import TextToImageRequest, TextToVideoRequest, ImageToVideoRequest, TextToSpeechRequest

router = APIRouter()


@router.post("/api/multimodal/text-to-image")
async def text_to_image(request: TextToImageRequest):
    if not state.swarm:
        raise HTTPException(status_code=503, detail="服务未初始化，请先配置 API Key")
    try:
        result = await state.swarm.qwen_client.text_to_image(
            prompt=request.prompt, model=request.model, size=request.size,
            n=request.n, negative_prompt=request.negative_prompt, seed=request.seed,
        )
        if result["success"]:
            await state.broadcast("multimodal_result", {
                "type": "text_to_image", "prompt": request.prompt, "images": result["images"],
            })
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/multimodal/text-to-video")
async def text_to_video(request: TextToVideoRequest):
    if not state.swarm:
        raise HTTPException(status_code=503, detail="服务未初始化，请先配置 API Key")
    try:
        result = await state.swarm.qwen_client.text_to_video(
            prompt=request.prompt, model=request.model, size=request.size,
            duration=request.duration, seed=request.seed,
        )
        if result["success"]:
            await state.broadcast("multimodal_task_submitted", {
                "type": "text_to_video", "prompt": request.prompt, "task_id": result["task_id"],
            })
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/multimodal/image-to-video")
async def image_to_video(request: ImageToVideoRequest):
    if not state.swarm:
        raise HTTPException(status_code=503, detail="服务未初始化，请先配置 API Key")
    try:
        result = await state.swarm.qwen_client.image_to_video(
            image_url=request.image_url, prompt=request.prompt,
            model=request.model, duration=request.duration, seed=request.seed,
        )
        if result["success"]:
            await state.broadcast("multimodal_task_submitted", {
                "type": "image_to_video", "image_url": request.image_url,
                "prompt": request.prompt, "task_id": result["task_id"],
            })
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/multimodal/video-task/{task_id}")
async def get_video_task_status(task_id: str):
    if not state.swarm:
        raise HTTPException(status_code=503, detail="服务未初始化，请先配置 API Key")
    try:
        result = await state.swarm.qwen_client.get_video_task_result(task_id)
        if result["success"] and result.get("status") == "completed":
            await state.broadcast("multimodal_result", {
                "type": "video", "task_id": task_id, "video_url": result["video_url"],
            })
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/multimodal/text-to-speech")
async def text_to_speech(request: TextToSpeechRequest):
    if not state.swarm:
        raise HTTPException(status_code=503, detail="服务未初始化，请先配置 API Key")
    try:
        result = await state.swarm.qwen_client.text_to_speech(
            text=request.text, model=request.model, voice=request.voice, format=request.format,
        )
        if result["success"]:
            audio_base64 = base64.b64encode(result["audio_data"]).decode("utf-8")
            await state.broadcast("multimodal_result", {
                "type": "text_to_speech",
                "text": request.text[:50] + "..." if len(request.text) > 50 else request.text,
                "voice": request.voice,
            })
            return {"success": True, "audio_base64": audio_base64, "format": result["format"]}
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/multimodal/voices")
async def list_available_voices():
    """获取可用的语音音色列表"""
    return {
        "voices": [
            {"id": "longxiaochun", "name": "龙小淳", "description": "温柔女声", "gender": "female"},
            {"id": "longxiaoxia", "name": "龙小夏", "description": "活泼女声", "gender": "female"},
            {"id": "longshuo", "name": "龙硕", "description": "成熟男声", "gender": "male"},
            {"id": "longyuan", "name": "龙远", "description": "磁性男声", "gender": "male"},
        ]
    }
