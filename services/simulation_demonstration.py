"""Stateless simulation previews and selected Excel exports; no writes or transport."""
import json
import os
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.auth.middleware import require_admin
from geofencing import point_in_polygon
from services.httpsms_export import build_workbook, normalize_phone, MISSING_SENDER
from services.simulation_route import calculate_local_evacuation
from services.simulation_mode_service import SimulationModeService
from services.httpsms_export import build_location_workbook, select_sms_recipients
from database.connection import get_db
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, func
from database.models import User

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'web-ui' / 'src' / 'data' / 'simulationConfig.json').read_text(encoding='utf-8'))
router = APIRouter(prefix='/admin/simulation/visual', tags=['Admin demonstration'])


def build_scenario(location: str, risk: str) -> dict:
    if location not in CONFIG['locations'] or risk not in CONFIG['risk_levels']:
        raise ValueError('Select a supported simulation location and HIGH or CRITICAL risk.')
    profile = CONFIG['locations'][location]
    ring = profile['dangerZones'][risk]
    people = []
    for index, person in enumerate(profile['users'], 1):
        latitude, longitude = person['latitude'], person['longitude']
        inside = point_in_polygon(latitude, longitude, ring)
        people.append({'displayId': f'Person {index}', 'latitude': latitude, 'longitude': longitude,
                       'inside': inside, 'recipientEligible': inside, 'phone': f'+9100000000{index:02d}'})
    evacuation = calculate_local_evacuation(people, ring, CONFIG['evacuation'], profile, risk)
    def feature(name, level, coordinates):
        return {'type': 'Feature', 'properties': {'name': name, 'risk_level': level, 'is_simulation': True},
                'geometry': {'type': 'Polygon', 'coordinates': [coordinates]}}
    message = (f"SIMULATION ONLY — LANDSENSE {'CRITICAL ALERT' if risk == 'CRITICAL' else 'ALERT'}: "
               f"You are currently inside the {location} {risk.lower()}-risk danger zone. "
               'Evacuate immediately using the recommended safe route to the simulated assembly area. '
               'Stay away from unstable slopes and follow official safety instructions. Do not return until the area is declared safe.')
    danger_zone = feature(location, risk, ring)
    actor = SimulationModeService.admin_actor(location, risk, profile.get('center'), danger_zone)
    return {'location': location, 'risk': risk, 'people': people, 'adminActor': actor,
            'dangerZone': danger_zone,
            'safeZone': feature(evacuation['safe_area_name'], 'SAFE', evacuation['safe_ring']),
            'route': {'route': {'status': 'ok', 'path': evacuation['path'], 'distance_meters': evacuation['distance_meters'],
                              'estimated_minutes': evacuation['estimated_minutes'], 'boundary_distance_meters': evacuation['boundary_distance_meters'],
                              'exit_point': evacuation['exit_point'], 'exit_index': evacuation['exit_index'], 'candidate_count': evacuation['candidate_count'],
                              'candidate_total': evacuation['candidate_total'], 'rejected_candidates': evacuation['rejected_candidates'],
                              'safe_area_id': evacuation['safe_area_id'], 'road_names': evacuation['road_names'], 'osm_way_ids': evacuation['osm_way_ids']},
                      'safe_zone': {'name': evacuation['safe_area_name'], **evacuation['destination']}, 'is_simulation': True},
            'message': message, 'note': CONFIG['note']}


class DemoWorkbookRequest(BaseModel):
    location: str
    risk: Literal['HIGH', 'CRITICAL']
    message: str = Field(min_length=1, max_length=1000)
    recipient_ids: list[str] = Field(default_factory=list, max_length=500)


@router.get('/scenario')
def scenario(location: str = 'Madikeri', risk: str = 'HIGH', _: dict = Depends(require_admin)):
    try:
        return build_scenario(location, risk)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/excel')
def excel(req: DemoWorkbookRequest, _: dict = Depends(require_admin)):
    try:
        demo = build_scenario(req.location, req.risk)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail='Enter a message before generating Excel.')
    sender = normalize_phone(os.getenv('HTTPSMS_FROM_NUMBER', ''))
    if not sender:
        raise HTTPException(status_code=422, detail=MISSING_SENDER)
    # Never accept recipient phones/inside flags from the browser. Recompute them.
    eligible = {person['displayId']: person for person in demo['people'] if person['inside']}
    selected = set(req.recipient_ids)
    if not selected or not selected.issubset(eligible):
        raise HTTPException(status_code=422, detail='Explicitly select only eligible recipients.')
    phones = [eligible[identifier]['phone'] for identifier in sorted(selected)]
    # Non-dialable recipients ensure a demo workbook cannot contact real people.
    content = build_workbook(sender, phones, message if message.startswith('SIMULATION ONLY') else 'SIMULATION ONLY — ' + message)
    date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    filename = f'LandSense_{req.location}_{req.risk}_SMS_{date}.xlsx'
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"',
                             'Cache-Control': 'no-store', 'X-Recipient-Count': str(len(phones))})


def registered_scenario(location: str, risk: str, db: Session) -> tuple[dict, list[dict]]:
    """Reuse approved simulation polygons and real saved locations; never create users."""
    from backend_api import _feature_population, _public_population_member, _safe_citizen_id, _mask_phone
    try:
        demo = build_scenario(location, risk)
        total, members = _feature_population(demo['dangerZone'], db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail='Unable to retrieve registered user locations.') from exc
    for member in members:
        member['sms_eligible'] = bool(member['inside'] and member['_alert_enabled'] and normalize_phone(member['_phone_number']))
    identifiers = [_safe_citizen_id(member['_user_id']) for member in members]
    if len(identifiers) != len(set(identifiers)):
        raise HTTPException(status_code=409, detail='Recipient identifiers are ambiguous. Export is unavailable.')
    demo['people'] = [{**_public_population_member(member),
                       'phone': _mask_phone(member['_phone_number']),
                       'recipientEligible': member['sms_eligible']} for member in members]
    demo['message'] = 'SIMULATION ONLY — ' + SimulationModeService._kodagu_message(risk, location)
    demo['total_registered_users'] = total
    demo['revision'] = hashlib.sha256(repr((location, risk, demo['dangerZone'], sorted(
        (_safe_citizen_id(m['_user_id']), m['_phone_number'], m['inside'], m['sms_eligible'], m['latitude'], m['longitude'])
        for m in members))).encode()).hexdigest()
    return demo, members


class RegisteredSelection(DemoWorkbookRequest):
    revision: str = Field(min_length=1, max_length=100)
    demo_admin_recipient_ids: list[str] = Field(default_factory=list, max_length=500)


class RegisteredWorkbookRequest(BaseModel):
    scenarios: list[RegisteredSelection] = Field(min_length=1, max_length=10)


def demo_admin_directory(operator: dict, db: Session) -> tuple[list[dict], dict[str, str]]:
    """Read other Admin accounts independently of saved locations and alert opt-in."""
    operator_id = operator.get('sub')
    if not isinstance(operator_id, str) or not operator_id.strip():
        raise HTTPException(status_code=403, detail='Authenticated simulation operator is required.')
    from backend_api import _mask_phone
    try:
        users = db.scalars(select(User).where(
            func.lower(func.trim(User.role)) == 'admin', User.uid != operator_id,
        ).order_by(User.name, User.uid)).all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail='Unable to retrieve Demo Admin recipients.') from exc
    recipients, phones, seen = [], {}, set()
    for user in users:
        identifier = 'demo-admin-' + hashlib.sha256(str(user.uid).encode()).hexdigest()
        if identifier in seen:
            raise HTTPException(status_code=409, detail='Demo Admin identifiers are ambiguous.')
        seen.add(identifier)
        phone = normalize_phone(user.phone_number)
        recipients.append({'recipientId': identifier, 'name': user.name or 'Admin',
                           'phone': _mask_phone(user.phone_number), 'selectable': bool(phone)})
        if phone:
            phones[identifier] = phone
    return recipients, phones


@router.get('/demo-admin-recipients')
def demo_admin_recipients(operator: dict = Depends(require_admin), db: Session = Depends(get_db)):
    recipients, _phones = demo_admin_directory(operator, db)
    return Response(json.dumps({'recipients': recipients}), media_type='application/json',
                    headers={'Cache-Control': 'no-store'})


@router.get('/recipients')
def registered_recipients(location: str, risk: str, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    demo, _members = registered_scenario(location, risk, db)
    return demo


@router.post('/registered-excel')
def registered_excel(req: RegisteredWorkbookRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    from backend_api import _safe_citizen_id
    sender = normalize_phone(os.getenv('HTTPSMS_FROM_NUMBER', ''))
    if not sender:
        raise HTTPException(status_code=422, detail=MISSING_SENDER)
    admin_phones = {}
    if any(selection.demo_admin_recipient_ids for selection in req.scenarios):
        _recipients, admin_phones = demo_admin_directory(_, db)
    sheets, seen = [], set()
    for selection in req.scenarios:
        key = (selection.location, selection.risk)
        if key in seen:
            raise HTTPException(status_code=422, detail='Duplicate location/risk selection.')
        seen.add(key)
        demo, members = registered_scenario(selection.location, selection.risk, db)
        if demo['revision'] != selection.revision:
            raise HTTPException(status_code=409, detail='User locations or eligibility changed. Refresh recipients and select again.')
        selected = set(selection.recipient_ids)
        eligible = {_safe_citizen_id(m['_user_id']) for m in members if m['sms_eligible']}
        selected_admins = set(selection.demo_admin_recipient_ids)
        if not selected.issubset(eligible):
            raise HTTPException(status_code=422, detail='Explicitly select only eligible recipients for each location.')
        if not selected_admins.issubset(admin_phones):
            raise HTTPException(status_code=422, detail='Select only available Demo Admin accounts other than the simulation operator. Refresh recipients and select again.')
        if not selected and not selected_admins:
            raise HTTPException(status_code=422, detail='Select at least one recipient to generate the httpSMS Excel.')
        message = selection.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail='Enter a simulation message before generating Excel.')
        result = select_sms_recipients([m for m in members if _safe_citizen_id(m['_user_id']) in selected])
        phones = sorted(set(result['_phones']) | {admin_phones[identifier] for identifier in selected_admins})
        sheets.append((f'{selection.location} {selection.risk}', phones,
                       f'SIMULATION ONLY — {selection.location} / {selection.risk}: {message}'))
    content = build_location_workbook(sender, sheets)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="LandSense_Selected_Simulation_httpSMS.xlsx"',
                             'Cache-Control': 'no-store', 'X-Recipient-Count': str(sum(len(s[1]) for s in sheets))})
