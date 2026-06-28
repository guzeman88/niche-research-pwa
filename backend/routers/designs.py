"""Design generation router - key-backed image provider adapters."""
from __future__ import annotations

import base64
import os
from typing import Any, Literal, cast

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/designs", tags=["designs"])

ProviderId = Literal[
    "ideogram",
    "recraft",
    "krea",
    "openai",
    "firefly",
    "stability",
    "fal",
    "replicate",
    "bfl",
    "gemini",
    "luma",
    "magnific",
    "leonardo",
    "midjourney",
]
ProviderStatus = Literal["ready", "needs_key", "manual", "unsupported", "billing_locked"]


class ProviderInfo(BaseModel):
    id: str
    label: str
    configured: bool
    available: bool
    status: ProviderStatus
    detail: str
    env_vars: list[str]


class DesignGenerateRequest(BaseModel):
    provider: ProviderId
    prompt: str = Field(min_length=8, max_length=4000)
    product_type: str | None = None
    aspect_ratio: str = "1:1"


class DesignGenerateResponse(BaseModel):
    provider: str
    title: str
    prompt: str
    asset_url: str
    content_type: str
    type: Literal["image"]
    meta: dict[str, Any] = Field(default_factory=dict)


PROVIDERS: dict[str, dict[str, Any]] = {
    "ideogram": {
        "label": "Ideogram",
        "env_vars": ["IDEOGRAM_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Best for text-heavy merch designs and slogan concepts.",
    },
    "recraft": {
        "label": "Recraft",
        "env_vars": ["RECRAFT_API_TOKEN"],
        "free_tier_candidate": False,
        "detail": "Best for clean production design assets and vector-style art.",
    },
    "krea": {
        "label": "Krea",
        "env_vars": ["KREA_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Best for testing multiple curated image models through one API.",
    },
    "openai": {
        "label": "OpenAI",
        "env_vars": ["OPENAI_API_KEY"],
        "free_tier_candidate": False,
        "detail": "General-purpose high-quality image generation.",
    },
    "stability": {
        "label": "Stability",
        "env_vars": ["STABILITY_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Fast image generation using Stability AI image services.",
    },
    "firefly": {
        "label": "Firefly",
        "env_vars": ["FIREFLY_SERVICES_CLIENT_ID", "FIREFLY_SERVICES_CLIENT_SECRET"],
        "free_tier_candidate": False,
        "detail": "Requires Adobe Firefly Services OAuth server-to-server access.",
    },
    "fal": {
        "label": "fal",
        "env_vars": ["FAL_KEY"],
        "free_tier_candidate": False,
        "detail": "Unified API for fast production image models including Flux, Ideogram, GPT Image, and Nano Banana.",
    },
    "replicate": {
        "label": "Replicate",
        "env_vars": ["REPLICATE_API_TOKEN"],
        "free_tier_candidate": False,
        "detail": "Runs hosted image models such as Flux, Stable Diffusion, Ideogram, and Recraft through one API.",
    },
    "bfl": {
        "label": "BFL Flux",
        "env_vars": ["BFL_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Official Black Forest Labs Flux API for high-quality prompt following and visual quality.",
    },
    "gemini": {
        "label": "Gemini",
        "env_vars": ["GEMINI_API_KEY"],
        "free_tier_candidate": True,
        "detail": "Free-tier candidate only when the Google project has no billing enabled and the selected image model is covered by free quota.",
    },
    "luma": {
        "label": "Luma",
        "env_vars": ["LUMA_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Dream Machine image generation for polished product and campaign visuals.",
    },
    "magnific": {
        "label": "Magnific",
        "env_vars": ["MAGNIFIC_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Text-to-image API focused on high-detail creative visuals.",
    },
    "leonardo": {
        "label": "Leonardo",
        "env_vars": ["LEONARDO_API_KEY"],
        "free_tier_candidate": False,
        "detail": "Commercial image API with Flux, Lucid, Phoenix, and production style presets.",
    },
    "midjourney": {
        "label": "Midjourney",
        "env_vars": [],
        "free_tier_candidate": False,
        "detail": "No public app-ready API is available; use manually as a quality benchmark.",
    },
}


@router.get("/providers", response_model=list[ProviderInfo])
def list_design_providers() -> list[ProviderInfo]:
    providers: list[ProviderInfo] = []
    for provider_id, meta in PROVIDERS.items():
        env_vars = list(meta["env_vars"])
        configured, status, available, detail = _provider_state(provider_id, meta)
        providers.append(
            ProviderInfo(
                id=provider_id,
                label=meta["label"],
                configured=configured,
                available=available,
                status=status,
                detail=detail,
                env_vars=env_vars,
            )
        )
    return providers


@router.post("/generate", response_model=DesignGenerateResponse)
async def generate_design(req: DesignGenerateRequest) -> DesignGenerateResponse:
    _require_generation_allowed(cast(str, req.provider))
    if req.provider == "ideogram":
        return await _generate_ideogram(req)
    if req.provider == "recraft":
        return await _generate_recraft(req)
    if req.provider == "krea":
        return await _generate_krea(req)
    if req.provider == "openai":
        return await _generate_openai(req)
    if req.provider == "stability":
        return await _generate_stability(req)
    if req.provider == "fal":
        return await _generate_fal(req)
    if req.provider == "replicate":
        return await _generate_replicate(req)
    if req.provider == "bfl":
        return await _generate_bfl(req)
    if req.provider == "gemini":
        return await _generate_gemini(req)
    if req.provider == "luma":
        return await _generate_luma(req)
    if req.provider == "magnific":
        return await _generate_magnific(req)
    if req.provider == "leonardo":
        return await _generate_leonardo(req)
    if req.provider == "firefly":
        raise HTTPException(status_code=501, detail="Firefly requires Adobe OAuth project-specific setup before generation can be safely enabled.")
    raise HTTPException(status_code=501, detail="This provider does not expose a supported public generation API.")


def _provider_state(provider_id: str, meta: dict[str, Any]) -> tuple[bool, ProviderStatus, bool, str]:
    env_vars = list(meta["env_vars"])
    configured = bool(env_vars) and all(bool(os.getenv(name)) for name in env_vars)
    if provider_id == "midjourney":
        return configured, "manual", False, meta["detail"]
    if provider_id == "firefly":
        status: ProviderStatus = "unsupported" if configured else "needs_key"
        return configured, status, False, meta["detail"]
    if not configured:
        return configured, "needs_key", False, meta["detail"]
    if _paid_generation_enabled():
        return configured, "ready", True, "Paid provider generation is explicitly enabled on the backend."
    if provider_id in _free_tier_allowlist():
        return configured, "ready", True, "Enabled for free-tier testing. Confirm the provider account has no billing attached before generating."
    if meta.get("free_tier_candidate"):
        detail = (
            "Key found, but generation is locked to avoid accidental charges. "
            f"After confirming free quota and no billing, set DESIGN_FREE_TIER_PROVIDERS={provider_id}."
        )
    else:
        detail = (
            "Key found, but this provider is billing-locked. "
            "Set DESIGN_ALLOW_PAID_PROVIDERS=1 only when you intentionally allow paid generation."
        )
    return configured, "billing_locked", False, detail


def _require_generation_allowed(provider_id: str) -> None:
    meta = PROVIDERS.get(provider_id)
    if not meta:
        raise HTTPException(status_code=400, detail="Unknown design provider.")
    _configured, status, available, detail = _provider_state(provider_id, meta)
    if status == "ready" and available:
        return
    if status == "needs_key":
        env_vars = ", ".join(meta["env_vars"])
        raise HTTPException(status_code=400, detail=f"{env_vars} is not configured on the backend.")
    if status == "billing_locked":
        raise HTTPException(status_code=402, detail=detail)
    raise HTTPException(status_code=501, detail=detail)


def _free_tier_allowlist() -> set[str]:
    raw = os.getenv("DESIGN_FREE_TIER_PROVIDERS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _paid_generation_enabled() -> bool:
    return os.getenv("DESIGN_ALLOW_PAID_PROVIDERS", "").strip().lower() in {"1", "true", "yes", "on"}


async def _generate_ideogram(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("IDEOGRAM_API_KEY")
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.ideogram.ai/v1/ideogram-v4/generate",
            headers={"Api-Key": key},
            files={
                "text_prompt": (None, req.prompt),
                "rendering_speed": (None, os.getenv("IDEOGRAM_RENDERING_SPEED", "TURBO")),
            },
        )
        data = _json_or_error(response, "Ideogram")
        image = _first(data.get("data"), "Ideogram returned no images")
        data_url, content_type = await _download_as_data_url(image["url"])
        return _response(req, data_url, content_type, {"seed": image.get("seed"), "resolution": image.get("resolution"), "safe": image.get("is_image_safe")})


async def _generate_recraft(req: DesignGenerateRequest) -> DesignGenerateResponse:
    token = _required_env("RECRAFT_API_TOKEN")
    model = os.getenv("RECRAFT_IMAGE_MODEL", "recraftv4_1")
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://external.api.recraft.ai/v1/images/generations",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "prompt": req.prompt,
                "n": 1,
                "model": model,
                "size": os.getenv("RECRAFT_IMAGE_SIZE", "1024x1024"),
                "response_format": "b64_json",
            },
        )
        data = _json_or_error(response, "Recraft")
        image = _first(data.get("data"), "Recraft returned no images")
        if image.get("b64_json"):
            return _response(req, _data_url(image["b64_json"], "image/png"), "image/png", {"model": model})
        if image.get("url"):
            data_url, content_type = await _download_as_data_url(image["url"])
            return _response(req, data_url, content_type, {"model": model})
    raise HTTPException(status_code=502, detail="Recraft response did not include an image.")


async def _generate_openai(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "prompt": req.prompt,
                "n": 1,
                "size": os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
                "quality": os.getenv("OPENAI_IMAGE_QUALITY", "medium"),
                "output_format": "png",
            },
        )
        data = _json_or_error(response, "OpenAI")
        image = _first(data.get("data"), "OpenAI returned no images")
        b64 = image.get("b64_json") or image.get("image_base64")
        if b64:
            return _response(req, _data_url(b64, "image/png"), "image/png", {"model": model})
        if image.get("url"):
            data_url, content_type = await _download_as_data_url(image["url"])
            return _response(req, data_url, content_type, {"model": model})
    raise HTTPException(status_code=502, detail="OpenAI response did not include an image.")


async def _generate_stability(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("STABILITY_API_KEY")
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={"Authorization": f"Bearer {key}", "Accept": "image/*"},
            files={
                "prompt": (None, req.prompt),
                "aspect_ratio": (None, req.aspect_ratio),
                "output_format": (None, "png"),
            },
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Stability error: {response.text[:300]}")
        content_type = response.headers.get("content-type", "image/png").split(";")[0]
        return _response(req, _data_url(base64.b64encode(response.content).decode("ascii"), content_type), content_type, {})


async def _generate_krea(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("KREA_API_KEY")
    endpoint = os.getenv("KREA_IMAGE_ENDPOINT", "https://api.krea.ai/generate/image/krea/krea-2/medium")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            endpoint,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"prompt": req.prompt, "aspect_ratio": req.aspect_ratio, "resolution": os.getenv("KREA_IMAGE_RESOLUTION", "1K")},
        )
        job = _json_or_error(response, "Krea")
        for _ in range(24):
            if job.get("status") == "completed":
                urls = ((job.get("result") or {}).get("urls") or [])
                image_url = _first(urls, "Krea completed without image URLs")
                data_url, content_type = await _download_as_data_url(image_url)
                return _response(req, data_url, content_type, {"job_id": job.get("job_id")})
            if job.get("status") in {"failed", "cancelled"}:
                raise HTTPException(status_code=502, detail=f"Krea generation failed: {job.get('error')}")
            await _sleep(2)
            job_id = job.get("job_id")
            poll = await client.get(f"https://api.krea.ai/jobs/{job_id}", headers={"Authorization": f"Bearer {key}"})
            job = _json_or_error(poll, "Krea")
    raise HTTPException(status_code=504, detail="Krea generation did not finish before timeout.")


async def _generate_fal(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("FAL_KEY")
    model = os.getenv("FAL_IMAGE_MODEL", "fal-ai/flux/schnell").strip("/")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://fal.run/{model}",
            headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
            json={
                "prompt": req.prompt,
                "image_size": "square_hd",
                "num_images": 1,
                "enable_safety_checker": True,
            },
        )
        data = _json_or_error(response, "fal")
        url = _extract_image_url(data, "fal returned no image URL")
        data_url, content_type = await _download_as_data_url(url)
        return _response(req, data_url, content_type, {"model": model})


async def _generate_replicate(req: DesignGenerateRequest) -> DesignGenerateResponse:
    token = _required_env("REPLICATE_API_TOKEN")
    model = os.getenv("REPLICATE_IMAGE_MODEL", "black-forest-labs/flux-schnell").strip("/")
    if "/" not in model:
        raise HTTPException(status_code=400, detail="REPLICATE_IMAGE_MODEL must look like owner/model.")
    owner, name = model.split("/", 1)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://api.replicate.com/v1/models/{owner}/{name}/predictions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "wait=60",
            },
            json={"input": {"prompt": req.prompt}},
        )
        data = _json_or_error(response, "Replicate")
        for _ in range(24):
            if data.get("status") == "succeeded":
                url = _extract_image_url(data.get("output"), "Replicate completed without an image URL")
                data_url, content_type = await _download_as_data_url(url)
                return _response(req, data_url, content_type, {"model": model, "prediction_id": data.get("id")})
            if data.get("status") in {"failed", "canceled"}:
                raise HTTPException(status_code=502, detail=f"Replicate generation failed: {data.get('error')}")
            get_url = (data.get("urls") or {}).get("get")
            if not get_url:
                break
            await _sleep(2)
            poll = await client.get(get_url, headers={"Authorization": f"Bearer {token}"})
            data = _json_or_error(poll, "Replicate")
    raise HTTPException(status_code=504, detail="Replicate generation did not finish before timeout.")


async def _generate_bfl(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("BFL_API_KEY")
    endpoint = os.getenv("BFL_IMAGE_ENDPOINT", "flux-2-pro-preview").strip("/")
    width, height = _square_dimensions()
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://api.bfl.ai/v1/{endpoint}",
            headers={"x-key": key, "accept": "application/json", "Content-Type": "application/json"},
            json={"prompt": req.prompt, "width": width, "height": height},
        )
        data = _json_or_error(response, "BFL")
        polling_url = data.get("polling_url")
        if not polling_url:
            raise HTTPException(status_code=502, detail="BFL did not return a polling URL.")
        for _ in range(60):
            await _sleep(1)
            poll = await client.get(polling_url, headers={"x-key": key, "accept": "application/json"})
            result = _json_or_error(poll, "BFL")
            status = result.get("status")
            if status == "Ready":
                url = ((result.get("result") or {}).get("sample"))
                if not url:
                    raise HTTPException(status_code=502, detail="BFL completed without an image URL.")
                data_url, content_type = await _download_as_data_url(url)
                return _response(req, data_url, content_type, {"endpoint": endpoint, "id": data.get("id")})
            if status in {"Error", "Failed"}:
                raise HTTPException(status_code=502, detail=f"BFL generation failed: {str(result)[:300]}")
    raise HTTPException(status_code=504, detail="BFL generation did not finish before timeout.")


async def _generate_gemini(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("GEMINI_API_KEY")
    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={
                "model": model,
                "input": req.prompt,
                "response_format": {"type": "image", "mime_type": "image/png", "aspect_ratio": req.aspect_ratio},
            },
        )
        data = _json_or_error(response, "Gemini")
        b64 = _extract_base64_image(data)
        if not b64:
            raise HTTPException(status_code=502, detail="Gemini response did not include an image.")
        return _response(req, _data_url(b64, "image/png"), "image/png", {"model": model, "interaction_id": data.get("id")})


async def _generate_luma(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("LUMA_API_KEY")
    model = os.getenv("LUMA_IMAGE_MODEL", "photon-1")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.lumalabs.ai/dream-machine/v1/generations/image",
            headers={"authorization": f"Bearer {key}", "accept": "application/json", "content-type": "application/json"},
            json={"prompt": req.prompt, "aspect_ratio": req.aspect_ratio, "model": model},
        )
        data = _json_or_error(response, "Luma")
        generation_id = data.get("id")
        for _ in range(60):
            if data.get("state") == "completed":
                url = ((data.get("assets") or {}).get("image"))
                if not url:
                    raise HTTPException(status_code=502, detail="Luma completed without an image URL.")
                data_url, content_type = await _download_as_data_url(url)
                return _response(req, data_url, content_type, {"model": model, "generation_id": generation_id})
            if data.get("state") == "failed":
                raise HTTPException(status_code=502, detail=f"Luma generation failed: {data.get('failure_reason')}")
            if not generation_id:
                break
            await _sleep(2)
            poll = await client.get(
                f"https://api.lumalabs.ai/dream-machine/v1/generations/{generation_id}",
                headers={"authorization": f"Bearer {key}", "accept": "application/json"},
            )
            data = _json_or_error(poll, "Luma")
    raise HTTPException(status_code=504, detail="Luma generation did not finish before timeout.")


async def _generate_magnific(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("MAGNIFIC_API_KEY")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.magnific.com/v1/ai/text-to-image",
            headers={"x-magnific-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
            json={
                "prompt": req.prompt,
                "negative_prompt": "blurry, distorted, low quality, unreadable text, watermark",
                "guidance_scale": 2,
                "num_images": 1,
                "image": {"size": "square_1_1"},
                "filter_nsfw": True,
            },
        )
        data = _json_or_error(response, "Magnific")
        url = _extract_image_url(data, "Magnific returned no image URL")
        data_url, content_type = await _download_as_data_url(url)
        return _response(req, data_url, content_type, {})


async def _generate_leonardo(req: DesignGenerateRequest) -> DesignGenerateResponse:
    key = _required_env("LEONARDO_API_KEY")
    model_id = os.getenv("LEONARDO_MODEL_ID", "7b592283-e8a7-4c5a-9ba6-d18c31f258b9")
    style_uuid = os.getenv("LEONARDO_STYLE_UUID", "1fbb6a68-9319-44d2-8d56-2957ca0ece6a")
    headers = {"authorization": f"Bearer {key}", "accept": "application/json", "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers,
            json={
                "alchemy": False,
                "height": 1024,
                "width": 1024,
                "modelId": model_id,
                "styleUUID": style_uuid,
                "contrast": 3.5,
                "num_images": 1,
                "prompt": req.prompt,
                "ultra": False,
            },
        )
        data = _json_or_error(response, "Leonardo")
        generation_id = (
            data.get("generationId")
            or (data.get("sdGenerationJob") or {}).get("generationId")
            or data.get("id")
        )
        if not generation_id:
            raise HTTPException(status_code=502, detail="Leonardo did not return a generationId.")
        for _ in range(60):
            await _sleep(2)
            poll = await client.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}", headers=headers)
            result = _json_or_error(poll, "Leonardo")
            url = _extract_image_url(result, "")
            if url:
                data_url, content_type = await _download_as_data_url(url)
                return _response(req, data_url, content_type, {"model_id": model_id, "generation_id": generation_id})
    raise HTTPException(status_code=504, detail="Leonardo generation did not finish before timeout.")


async def _download_as_data_url(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Could not download generated image: {response.status_code}")
        content_type = response.headers.get("content-type", "image/png").split(";")[0]
        encoded = base64.b64encode(response.content).decode("ascii")
        return _data_url(encoded, content_type), content_type


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{name} is not configured on the backend.")
    return value


def _json_or_error(response: httpx.Response, provider: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"{provider} error: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"{provider} returned non-JSON response.") from exc


def _first(values: Any, message: str) -> Any:
    if not values:
        raise HTTPException(status_code=502, detail=message)
    return values[0]


def _extract_image_url(value: Any, message: str) -> str:
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, list):
        for item in value:
            try:
                return _extract_image_url(item, message)
            except HTTPException:
                continue
    if isinstance(value, dict):
        for key in ("url", "image", "image_url", "sample"):
            found = value.get(key)
            if isinstance(found, str) and found.startswith("http"):
                return found
        for key in ("images", "data", "output", "assets", "generated_images", "generations_by_pk"):
            found = value.get(key)
            if found:
                try:
                    return _extract_image_url(found, message)
                except HTTPException:
                    continue
    raise HTTPException(status_code=502, detail=message or "Provider response did not include an image URL.")


def _extract_base64_image(value: Any) -> str | None:
    if isinstance(value, dict):
        output_image = value.get("output_image")
        if isinstance(output_image, dict) and output_image.get("data"):
            return str(output_image["data"])
        if value.get("type") == "image" and value.get("data"):
            return str(value["data"])
        for key in ("steps", "output", "content"):
            found = value.get(key)
            b64 = _extract_base64_image(found)
            if b64:
                return b64
    if isinstance(value, list):
        for item in value:
            b64 = _extract_base64_image(item)
            if b64:
                return b64
    return None


def _square_dimensions() -> tuple[int, int]:
    size = int(os.getenv("BFL_IMAGE_SIZE", "1024"))
    return size, size


def _data_url(b64: str, content_type: str) -> str:
    return f"data:{content_type};base64,{b64}"


def _response(req: DesignGenerateRequest, asset_url: str, content_type: str, meta: dict[str, Any]) -> DesignGenerateResponse:
    return DesignGenerateResponse(
        provider=cast(str, req.provider),
        title=f"{req.provider} design",
        prompt=req.prompt,
        asset_url=asset_url,
        content_type=content_type,
        type="image",
        meta=meta,
    )


async def _sleep(seconds: int) -> None:
    import asyncio

    await asyncio.sleep(seconds)
