"""Site registry, validated placement and sanitized floor-plan files."""
import asyncio
import hashlib
import importlib
import inspect
import logging
import os
from io import BytesIO
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Annotated, Literal
import unicodedata
from urllib.parse import urlencode
import warnings

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from python_multipart.exceptions import MultipartParseError
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.datastructures import UploadFile

from .signing import sign_url, verify_url

PLAN_DIR = Path(__file__).resolve().parents[1] / 'state' / 'plans'
MAX_PLAN_BYTES = 8 * 1024 * 1024
log = logging.getLogger(__name__)


def clean_name(value):
    if any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Control characters are not allowed.')
    value = value.strip()
    if not 1 <= len(value) <= 60: raise ValueError('Use 1 to 60 characters.')
    return value


def clean_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value):
        raise ValueError('Enter a valid email address.')
    local = value.split('@')[0]
    if len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in local:
        raise ValueError('Enter a valid email address.')
    return value


Name = Annotated[str, AfterValidator(clean_name)]
Email = Annotated[str, AfterValidator(clean_email)]
Unit = Annotated[float, Field(ge=0, le=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class NameInput(Input):
    name: Name


class FloorPatch(Input):
    name: Name | None = None
    order: int | None = Field(default=None, ge=0)
    metersPerUnit: float | None = Field(default=None, gt=0, le=10)

    @model_validator(mode='after')
    def required_values(self):
        reject_null(self, 'name', 'order')
        return self


class Post(Input):
    x: Unit
    y: Unit


class Placement(Post):
    floorId: str = Field(min_length=1, max_length=100)
    angle: float = Field(ge=0, le=360)
    fov: float = Field(ge=10, le=170)
    range: float = Field(ge=.02, le=1)


def reject_null(model, *fields):
    if any(field in model.model_fields_set and getattr(model, field) is None for field in fields):
        raise ValueError('This field cannot be null.')


class GPS(Input):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float = Field(ge=0, le=10000000)
    capturedAt: float = Field(ge=0)


class CameraPatch(Input):
    name: Name | None = None
    building: Name | None = None
    floor: Name | None = None
    enabled: bool | None = None
    label: Name | None = None
    placement: Placement | None = None
    gps: GPS | None = None

    @model_validator(mode='after')
    def required_values(self):
        reject_null(self, 'name', 'building', 'floor', 'enabled', 'label')
        return self


class GuardInput(Input):
    callsign: str = Field(pattern=r'^G[0-9]{1,2}$')
    name: Name
    email: Email | None = None
    floorId: str | None = Field(default=None, min_length=1, max_length=100)
    floorName: Name | None = None
    post: Post | None = None


class GuardPatch(Input):
    callsign: str | None = Field(default=None, pattern=r'^G[0-9]{1,2}$')
    name: Name | None = None
    email: Email | None = None
    floorId: str | None = Field(default=None, min_length=1, max_length=100)
    floorName: Name | None = None
    post: Post | None = None
    shift: Literal['on_shift', 'break', 'off'] | None = None

    @model_validator(mode='after')
    def required_values(self):
        reject_null(self, 'callsign', 'name', 'shift')
        return self


class GuardProfile(Input):
    floorName: Name | None


def camera_payload(camera):
    placement = None if camera['floor_id'] is None else dict(floorId=camera['floor_id'], **{
        key: camera[key] for key in ('x', 'y', 'angle', 'fov', 'range')})
    # Preserve all existing metadata fields for legacy clients.
    return {**camera, 'enabled': bool(camera['enabled']), 'placement': placement}


def floor_payload(floor):
    plan = None
    if floor['sample']:
        plan = dict(url='/demo/mall/plan.svg', width=1000, height=620)
    elif floor['plan_path']:
        path = f"/api/v2/files/plan/{floor['id']}?" + urlencode({'v': floor['plan_hash']})
        plan = dict(url=sign_url(path), width=floor['plan_w'], height=floor['plan_h'])
    return dict(id=floor['id'], name=floor['name'], order=floor['ord'], plan=plan,
                sample=bool(floor['sample']), metersPerUnit=floor['meters_per_unit'])


def guard_payload(guard):
    return dict(id=guard['id'], callsign=guard['callsign'], name=guard['name'], userId=guard['user_id'],
                email=guard['email'], floorId=guard['floor_id'], floorName=guard['floor_name'], gps=guard['gps'],
                post=None if guard['post_x'] is None else dict(x=guard['post_x'], y=guard['post_y']),
                shift=guard['shift'], presence=dict(online=False, lastSeen=None), push=False)


def role_dependency(classroom, role):
    try:
        from .auth import require_role
    except ImportError:
        # TODO(H1): remove the legacy fallback when auth.require_role is available.
        async def legacy(request: Request):
            result = classroom.require_admin(request)
            if inspect.isawaitable(result): await result
        return legacy
    return require_role(role)


def store_call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except KeyError as error:
        raise HTTPException(404, 'Record or floor not found') from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, 'Callsign, email or user is already assigned, or a field conflicts.') from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class PlanTooLarge(MultiPartException):
    pass


class PlanParser(MultiPartParser):
    def on_part_data(self, data, start, end):
        if self._current_part.file is not None:
            self.plan_bytes = getattr(self, 'plan_bytes', 0) + end - start
            if self.plan_bytes > MAX_PLAN_BYTES: raise PlanTooLarge('Plan must be at most 8 MB.')
        super().on_part_data(data, start, end)


async def read_plan(request):
    async def limited_stream():
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_PLAN_BYTES + 64 * 1024: raise PlanTooLarge('Plan must be at most 8 MB.')
            yield chunk
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'multipart/form-data':
        raise HTTPException(415, 'Use multipart/form-data with a file field.')
    parser = PlanParser(request.headers, limited_stream(), max_files=1, max_fields=0)
    try:
        form = await parser.parse()
    except PlanTooLarge as error:
        raise HTTPException(413, str(error)) from error
    except MultiPartException as error:
        raise HTTPException(422, str(error)) from error
    except MultipartParseError as error:
        raise HTTPException(422, 'Malformed multipart upload.') from error
    finally:
        # parse() does not close partial uploads for cancellation/parser errors.
        # Completed uploads are consumed below before their files are closed.
        if 'form' not in locals():
            for file in parser._files_to_close_on_error: file.close()
    try:
        upload = form.get('file')
        if not isinstance(upload, UploadFile): raise HTTPException(422, 'A file field is required.')
        return await upload.read(MAX_PLAN_BYTES + 1)
    finally:
        await form.close()


def sanitize_plan(data):
    if len(data) > MAX_PLAN_BYTES: raise HTTPException(413, 'Plan must be at most 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise HTTPException(415, 'Use a PNG, JPEG or WebP image.')
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                image = ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                # A fresh pixel-only image cannot carry EXIF, ICC, XMP or text chunks.
                clean = Image.new('RGBA', image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format='WEBP', lossless=True)
                return output.getvalue(), clean.width, clean.height
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(415, 'Invalid or unsafe PNG, JPEG or WebP image.') from error


def remove_plan(path):
    if path:
        resolved = Path(path).resolve()
        if resolved.parent != PLAN_DIR.resolve(): raise ValueError('Invalid plan storage path')
        resolved.unlink(missing_ok=True)


async def invite_guard(classroom, guard, *, origin=None):
    """H1 hook: invite_member(email=..., role='guard', callsign=...)."""
    if not guard['email']: return
    invite = getattr(getattr(classroom, 'auth', None), 'invite_member', None)
    if invite is None:
        for module_name in ('.auth', '.members'):
            try:
                module = importlib.import_module(module_name, __package__)
            except ModuleNotFoundError as error:
                if error.name != __package__ + module_name: raise
                continue
            invite = getattr(module, 'invite_member', None)
            if invite: break
    if invite is None:
        log.info('Guard stored; invitation integration is unavailable (H1).')
        return
    kwargs = dict(email=guard['email'], role='guard', callsign=guard['callsign'])
    if 'origin' in inspect.signature(invite).parameters: kwargs['origin'] = origin
    result = invite(**kwargs)
    if inspect.isawaitable(result): await result


def create_router(classroom):
    router = APIRouter(prefix='/api/v2')
    store = classroom.store
    serialize_guard = getattr(classroom, 'guard_payload', guard_payload)
    reader = [Depends(role_dependency(classroom, 'reviewer'))]
    admin = [Depends(role_dependency(classroom, 'admin'))]

    async def changed():
        await classroom.broadcast(classroom.snapshot())

    @router.get('/site', dependencies=reader)
    async def get_site(): return store.site()

    @router.patch('/site', dependencies=admin)
    async def patch_site(data: NameInput):
        result = store.update_site(data.name)
        await changed()
        return result

    @router.get('/floors', dependencies=reader)
    async def get_floors(): return [floor_payload(floor) for floor in store.floors()]

    @router.post('/floors', dependencies=admin, status_code=201)
    async def add_floor(data: NameInput):
        result = floor_payload(store.add_floor(data.name))
        await changed()
        return result

    @router.patch('/floors/{floor_id}', dependencies=admin)
    async def patch_floor(floor_id: str, data: FloorPatch):
        changes = data.model_dump(exclude_unset=True)
        if 'order' in changes: changes['ord'] = changes.pop('order')
        if 'metersPerUnit' in changes: changes['meters_per_unit'] = changes.pop('metersPerUnit')
        result = floor_payload(store_call(store.update_floor, floor_id, **changes))
        await changed()
        return result

    @router.delete('/floors/{floor_id}', dependencies=admin, status_code=204)
    async def delete_floor(floor_id: str):
        old = store_call(store.delete_floor, floor_id)
        remove_plan(old['plan_path'])
        await changed()
        return Response(status_code=204)

    @router.post('/floors/{floor_id}/sample', dependencies=admin)
    async def sample_floor(floor_id: str):
        old = store.floor(floor_id)
        if old is None: raise HTTPException(404, 'Floor not found')
        result = store.update_floor(floor_id, sample=1, plan_path=None, plan_hash=None, plan_w=1000, plan_h=620, meters_per_unit=.1)
        remove_plan(old['plan_path'])
        await changed()
        return floor_payload(result)

    @router.put('/floors/{floor_id}/plan', dependencies=admin)
    async def upload_plan(floor_id: str, request: Request):
        if store.floor(floor_id) is None: raise HTTPException(404, 'Floor not found')
        encoded, width, height = await asyncio.to_thread(sanitize_plan, await read_plan(request))
        # Re-read after await: another request may have replaced/deleted this floor.
        old = store.floor(floor_id)
        if old is None: raise HTTPException(404, 'Floor not found')
        digest = hashlib.sha256(encoded).hexdigest()
        PLAN_DIR.mkdir(parents=True, exist_ok=True)
        target = PLAN_DIR / f'{floor_id}-{digest}.webp'
        temporary = PLAN_DIR / f'.{floor_id}-{secrets.token_hex(12)}.tmp'
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, target)
            result = store.update_floor(floor_id, sample=0, plan_path=str(target), plan_w=width, plan_h=height, plan_hash=digest)
        except Exception:
            if str(target) != old['plan_path']: target.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        if old['plan_path'] != str(target): remove_plan(old['plan_path'])
        await changed()
        return floor_payload(result)

    @router.get('/files/plan/{floor_id}')
    async def plan_file(floor_id: str, request: Request):
        version = request.query_params.get('v', '')
        path = f'/api/v2/files/plan/{floor_id}?' + urlencode({'v': version})
        if not verify_url(path, request.query_params.get('exp', ''), request.query_params.get('sig', '')):
            raise HTTPException(403, 'Invalid or expired file signature')
        floor = store.floor(floor_id)
        if not floor or not floor['plan_path'] or floor['plan_hash'] != version:
            raise HTTPException(404, 'Plan not found')
        path = Path(floor['plan_path']).resolve()
        if path.parent != PLAN_DIR.resolve() or not path.is_file(): raise HTTPException(404, 'Plan not found')
        return FileResponse(path, media_type='image/webp', headers={'Cache-Control': 'private, max-age=300'})

    @router.get('/guards', dependencies=reader)
    async def get_guards(): return [serialize_guard(guard) for guard in store.guards()]

    @router.post('/guards', dependencies=admin, status_code=201)
    async def add_guard(data: GuardInput, request: Request):
        guard = store_call(store.add_guard, data.callsign, data.name, email=data.email,
                           floor_id=data.floorId, post=data.post.model_dump() if data.post else None, floor_name=data.floorName)
        await changed()
        try:
            await invite_guard(classroom, guard, origin=request.headers.get('origin'))
        except Exception as error:
            # Local persistence cannot be rolled back after an external invitation.
            # Give the caller the durable id and an explicit, safe retry route.
            log.warning('Guard invitation failed; guard record retained.')
            raise HTTPException(502, {'message': 'Guard saved; invitation failed. Retry via /api/v2/members/invite.',
                                      'guardId': guard['id']}) from error
        current = store.guard(guard['id'])
        if current is None: raise HTTPException(409, 'Guard was deleted while the invitation was pending.')
        return serialize_guard(current)

    @router.patch('/guards/{guard_id}', dependencies=admin)
    async def patch_guard(guard_id: str, data: GuardPatch):
        changes = data.model_dump(exclude_unset=True)
        if 'floorId' in changes: changes['floor_id'] = changes.pop('floorId')
        if 'floorName' in changes: changes['floor_name'] = changes.pop('floorName')
        old = store.guard(guard_id)
        guard = store_call(store.update_guard, guard_id, **changes)
        if old['callsign'] != guard['callsign']: await classroom.revoke_guard(guard=old['callsign'])
        await changed()
        return serialize_guard(guard)

    @router.delete('/guards/{guard_id}', dependencies=admin, status_code=204)
    async def delete_guard(guard_id: str):
        old = store_call(store.delete_guard, guard_id)
        await classroom.revoke_guard(guard=old['callsign'])
        await changed()
        return Response(status_code=204)

    return router
