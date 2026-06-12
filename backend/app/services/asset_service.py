# Location: ./backend/app/services/asset_service.py
#
# CHANGES FROM ORIGINAL:
#   + upload_csv() now calls asset_identifier_service.introspect_registry()
#     AFTER inserting rows, and stores the resulting schema snapshot in a
#     dedicated sentinel row (schema_meta column) so chat_service can
#     retrieve it cheaply without scanning the full table.
#
#   + Added get_schema_meta() helper — used by chat_service to load the
#     schema snapshot when generating dynamic questions.
#
#   All original functions (list_assets, get_asset, lookup_asset, delete_*,
#   get_asset_stats) are UNCHANGED.

import csv
import io
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
from fastapi import HTTPException

from app.models.asset import AssetRegistry


# ── Column name normaliser ────────────────────────────────────────────────────
# The CSV can have inconsistent casing / spacing — normalise to lowercase+underscore

def _norm(val: str) -> str:
    return val.strip().lower().replace(' ', '_').replace('-', '_')


# ── Static column map for the known dummy/template format ────────────────────
# Real CSVs may have columns NOT in this map — those are handled by the
# dynamic introspection path in asset_identifier_service.py.

COLUMN_MAP = {
    # ── Account / Cloud ───────────────────────────────────────────────────────
    'account_id':                     'account_id',
    'account_no':                     'account_id',
    'account_number':                 'account_id',
    'asset_id':                       'account_id',       # enterprise CMDB asset ID
    'cmdb_id':                        'account_id',       # alt
    'asset_tag':                      'account_id',       # alt
    'account_name':                   'account_name',
    'cloud_provider':                 'cloud_provider',
    'cloud':                          'cloud_provider',
    'c_cloud':                        'cloud_provider',

    # ── Location / Region ─────────────────────────────────────────────────────
    'region':                         'region',
    'dc_location':                    'region',
    'data_centre':                    'region',
    'data_center':                    'region',
    'location':                       'region',
    'cloud_region':                   'region',           # enterprise: CLOUD_REGION
    'rack_location':                  'availability_zone', # enterprise: RACK_LOCATION
    'availability_zone':              'availability_zone',
    'cloud_az':                       'availability_zone', # enterprise: CLOUD_AZ
    'az':                             'availability_zone',

    # ── Instance / Server ─────────────────────────────────────────────────────
    'instance_name':                  'instance_name',
    'server_name':                    'instance_name',
    'hostname':                       'instance_name',    # enterprise: HOSTNAME
    'host_name':                      'instance_name',
    'fqdn':                           'instance_name',    # enterprise: FQDN
    'device_name':                    'instance_name',
    'node_name':                      'instance_name',
    'instance_id':                    'vpc_id',           # enterprise: INSTANCE_ID → store in vpc_id

    # ── Network ───────────────────────────────────────────────────────────────
    'vpc_name':                       'vpc_name',
    'vpc_label':                      'vpc_name',
    'vpc_id':                         'vpc_id',
    'vlan_id':                        'vpc_name',         # enterprise: VLAN_ID
    'subnet':                         'vpc_name',         # enterprise: SUBNET
    'security_group':                 'vpc_id',           # enterprise: SECURITY_GROUP
    'private_ip_address':             'private_ip_address',
    'private_ip':                     'private_ip_address',
    'subnet_ip':                      'private_ip_address',
    'internal_ip':                    'private_ip_address',
    'ip_address':                     'private_ip_address', # enterprise: IP_ADDRESS
    'c_listen_ip':                    'private_ip_address',
    'public_ip_address':              'public_ip_address',
    'public_ip':                      'public_ip_address',
    'external_ip':                    'public_ip_address',
    'mac_address':                    'vpc_name',         # store MAC in vpc_name field

    # ── Application ───────────────────────────────────────────────────────────
    'c_application':                  'application',
    'application':                    'application',
    'application_name':               'application',      # enterprise: APPLICATION_NAME
    'application_owner':              'contact_email',    # enterprise: APPLICATION_OWNER → contact
    'app':                            'application',
    'app_name':                       'application',
    'service_name':                   'application',
    'workload':                       'application',

    # ── Environment ───────────────────────────────────────────────────────────
    'c_environment':                  'environment',
    'environment':                    'environment',
    'env':                            'environment',
    'env_type':                       'environment',
    'environment_type':               'environment',
    'deployment_env':                 'environment',
    # NOTE: 'tier' in the enterprise CSV means Service Tier (Tier-1/Tier-2),
    # NOT environment — so we map it to team_verticals instead
    'service_tier':                   'team_verticals',   # enterprise: SERVICE_TIER
    'sla_tier':                       'team_verticals',   # enterprise: SLA_TIER
    'criticality':                    'os_details',       # enterprise: CRITICALITY

    # ── Asset / Instance type ─────────────────────────────────────────────────
    'asset_type':                     'os_details',       # enterprise: ASSET_TYPE
    'instance_type':                  'os_details',       # enterprise: INSTANCE_TYPE (m5.4xlarge)
    'manufacturer':                   'os_details',       # enterprise: MANUFACTURER
    'model':                          'os_details',       # alt

    # ── Team / Ownership ─────────────────────────────────────────────────────
    'team_verticals':                 'team_verticals',
    'vertical':                       'team_verticals',
    'platform':                       'team_verticals',
    'technology':                     'team_verticals',
    'tech_stack':                     'team_verticals',
    'c_team':                         'team',
    'team':                           'team',
    'business_unit':                  'team',             # enterprise: BUSINESS_UNIT
    'department':                     'team',
    'squad':                          'team',
    'group':                          'team',
    'cost_centre':                    'account_name',     # enterprise: COST_CENTRE → account_name

    # ── Contact / Escalation emails ───────────────────────────────────────────
    'c_contact':                      'contact_email',
    'contact_email':                  'contact_email',
    'owner_email':                    'contact_email',
    'team_email':                     'contact_email',
    'primary_contact':                'contact_email',
    'primary_owner_email':            'contact_email',    # enterprise: PRIMARY_OWNER_EMAIL
    'secondary_owner_email':          'cloudops_manager_email', # enterprise: SECONDARY_OWNER_EMAIL
    'team_lead_email':                'cloudops_director_email', # enterprise: TEAM_LEAD_EMAIL
    'engineering_dev_manager_email':  'engineering_dev_manager_email',
    'it_manager_email':               'engineering_dev_manager_email', # enterprise: IT_MANAGER_EMAIL
    'manager_email':                  'engineering_dev_manager_email',
    'mgr_email':                      'engineering_dev_manager_email',
    'dev_manager_email':              'engineering_dev_manager_email',
    'engineering_dev_director_email': 'engineering_dev_director_email',
    'it_director_email':              'engineering_dev_director_email', # enterprise: IT_DIRECTOR_EMAIL
    'director_email':                 'engineering_dev_director_email',
    'dev_director_email':             'engineering_dev_director_email',
    'engineering_dev_director_emailcloudops_manager_email': 'engineering_dev_director_email',
    'cloudops_manager_email':         'cloudops_manager_email',
    'infra_ops_email':                'cloudops_manager_email',  # enterprise: INFRA_OPS_EMAIL
    'ops_manager_email':              'cloudops_manager_email',
    'cloudops_director_email':        'cloudops_director_email',
    'change_manager_email':           'cloudops_director_email', # enterprise: CHANGE_MANAGER_EMAIL
    'ops_director_email':             'cloudops_director_email',

    # ── OS ────────────────────────────────────────────────────────────────────
    'os_details':                     'os_details',
    'os_type':                        'os_details',
    'os_name':                        'os_distribution',  # enterprise: OS_NAME
    'os_version':                     'os_details',       # enterprise: OS_VERSION
    'os_distribution':                'os_distribution',
    'os':                             'os_distribution',
    'operating_system':               'os_distribution',

    # ── Power / State ─────────────────────────────────────────────────────────
    'power_state':                    'power_state',
    'power_status':                   'power_state',      # enterprise: POWER_STATUS
    'status':                         'power_state',
    'instance_state':                 'power_state',
    'lifecycle_status':               'power_state',      # enterprise: LIFECYCLE_STATUS
    'patch_status':                   'vpc_name',         # enterprise: PATCH_STATUS

    # ── Active flag ───────────────────────────────────────────────────────────
    'c_active':                       'is_active',
    'active_flag':                    'is_active',
    'is_active':                      'is_active',
    'active':                         'is_active',
    'monitoring_status':              'is_active',        # enterprise: MONITORING_STATUS
}


def _parse_csv(content: bytes) -> List[Dict]:
    """
    Parse CSV bytes into a list of normalised dicts.

    For columns NOT in COLUMN_MAP, we still preserve them under their
    normalised key so introspect_registry() can see the full picture.
    This is the key change that makes the system work with unknown CSVs.
    """
    text   = content.decode('utf-8', errors='ignore')
    reader = csv.DictReader(io.StringIO(text))
    records = []

    for row in reader:
        record = {}
        for raw_key, value in row.items():
            if not raw_key:
                continue
            norm_key = _norm(raw_key)
            # Map to known field if possible; otherwise keep normalised key
            mapped = COLUMN_MAP.get(norm_key, norm_key)
            if value and value.strip():
                record[mapped] = value.strip()
        if record:
            records.append(record)

    return records


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_csv(
    db: Session,
    content: bytes,
    uploaded_by: str,
    replace_all: bool = False,
) -> dict:
    """
    Parse and insert CSV rows into AssetRegistry.
    After insertion, runs introspect_registry() to build a schema snapshot
    and attaches it to the first inserted row (schema_meta column).

    The schema snapshot is used by asset_identifier_service.generate_questions()
    during the chat escalation flow — so the system always knows what
    fields and values are available to ask about, regardless of CSV structure.
    """
    records = _parse_csv(content)
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    if replace_all:
        db.query(AssetRegistry).delete()
        db.commit()

    inserted  = 0
    skipped   = 0
    first_row = None   # We'll attach schema_meta to this row

    for rec in records:
        if not any(rec.values()):
            skipped += 1
            continue

        asset = AssetRegistry(
            account_id                     = rec.get('account_id'),
            account_name                   = rec.get('account_name'),
            cloud_provider                 = rec.get('cloud_provider'),
            region                         = rec.get('region'),
            availability_zone              = rec.get('availability_zone'),
            instance_name                  = rec.get('instance_name'),
            vpc_name                       = rec.get('vpc_name'),
            vpc_id                         = rec.get('vpc_id'),
            private_ip_address             = rec.get('private_ip_address'),
            public_ip_address              = rec.get('public_ip_address'),
            application                    = rec.get('application'),
            environment                    = rec.get('environment'),
            team_verticals                 = rec.get('team_verticals'),
            team                           = rec.get('team'),
            contact_email                  = rec.get('contact_email'),
            engineering_dev_manager_email  = rec.get('engineering_dev_manager_email'),
            engineering_dev_director_email = rec.get('engineering_dev_director_email'),
            cloudops_manager_email         = rec.get('cloudops_manager_email'),
            cloudops_director_email        = rec.get('cloudops_director_email'),
            power_state                    = rec.get('power_state'),
            os_details                     = rec.get('os_details'),
            os_distribution                = rec.get('os_distribution'),
            is_active                      = rec.get('is_active', 'TRUE').upper() == 'TRUE',
            uploaded_by                    = uploaded_by,
        )
        db.add(asset)

        if first_row is None:
            first_row = asset

        inserted += 1

    db.commit()

    # ── Build and store schema snapshot ──────────────────────────────────────
    # Always introspect the FULL table after insert so the snapshot reflects
    # all uploaded CSVs combined (when replace_all=False and CSVs are appended).
    # Stored on the oldest row so it survives partial deletes.
    try:
        from app.services.asset_identifier_service import introspect_registry
        schema_meta = introspect_registry(db, domain_hint=None)
        anchor = (
            db.query(AssetRegistry)
            .order_by(AssetRegistry.created_at.asc())
            .first()
        )
        if anchor:
            anchor.schema_meta = schema_meta
            db.commit()
            logger.info("[AssetService] Schema snapshot refreshed — %d identifier columns, %d total assets",
                        len(schema_meta.get("columns", {})), schema_meta.get("total_assets", 0))
    except Exception as e:
        logger.warning("[AssetService] Schema snapshot generation failed (non-fatal): %s", e)

    return {
        "inserted": inserted,
        "skipped":  skipped,
        "total":    len(records),
        "message":  f"Successfully imported {inserted} assets",
    }


# ── Schema meta retrieval (NEW) ───────────────────────────────────────────────

def get_schema_meta(db: Session) -> Optional[dict]:
    """
    Retrieve the schema snapshot stored at upload time.
    Returns None if no assets have been uploaded yet or the column is empty.

    Used by chat_service to load asset field metadata cheaply,
    without re-scanning the full table on every chat turn.
    """
    row = (
        db.query(AssetRegistry)
        .filter(AssetRegistry.schema_meta.isnot(None))
        .order_by(AssetRegistry.created_at.asc())
        .first()
    )
    return row.schema_meta if row else None


# ── List / Search ─────────────────────────────────────────────────────────────
# UNCHANGED from original

def list_assets(
    db: Session,
    environment: Optional[str]    = None,
    team: Optional[str]           = None,
    cloud_provider: Optional[str] = None,
    power_state: Optional[str]    = None,
    search: Optional[str]         = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    query = db.query(AssetRegistry)

    if environment:
        query = query.filter(AssetRegistry.environment.ilike(f"%{environment}%"))
    if team:
        query = query.filter(AssetRegistry.team.ilike(f"%{team}%"))
    if cloud_provider:
        query = query.filter(AssetRegistry.cloud_provider.ilike(f"%{cloud_provider}%"))
    if power_state:
        query = query.filter(AssetRegistry.power_state.ilike(f"%{power_state}%"))
    if search:
        s = f"%{search.lower()}%"
        query = query.filter(
            (AssetRegistry.instance_name.ilike(s))     |
            (AssetRegistry.application.ilike(s))        |
            (AssetRegistry.team.ilike(s))               |
            (AssetRegistry.vpc_name.ilike(s))           |
            (AssetRegistry.private_ip_address.ilike(s)) |
            (AssetRegistry.public_ip_address.ilike(s))  |
            (AssetRegistry.account_name.ilike(s))
        )

    total  = query.count()
    assets = query.order_by(AssetRegistry.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total":  total,
        "assets": [_asset_to_dict(a) for a in assets],
    }


def get_asset(db: Session, asset_id: str) -> dict:
    asset = db.query(AssetRegistry).filter(AssetRegistry.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_to_dict(asset)


# ── Lookup for routing ────────────────────────────────────────────────────────
# UNCHANGED from original

def lookup_asset(
    db: Session,
    instance_name: Optional[str] = None,
    application: Optional[str]   = None,
    environment: Optional[str]   = None,
    team_vertical: Optional[str] = None,
    ip_address: Optional[str]    = None,
) -> Optional[dict]:
    """
    Find the best matching asset for routing.
    Returns the asset dict with ownership info, or None.
    """
    query = db.query(AssetRegistry)

    if instance_name:
        query = query.filter(AssetRegistry.instance_name.ilike(f"%{instance_name}%"))
    if application:
        query = query.filter(AssetRegistry.application.ilike(f"%{application}%"))
    if environment:
        query = query.filter(AssetRegistry.environment.ilike(f"%{environment}%"))
    if team_vertical:
        query = query.filter(AssetRegistry.team_verticals.ilike(f"%{team_vertical}%"))
    if ip_address:
        query = query.filter(
            (AssetRegistry.private_ip_address.ilike(f"%{ip_address}%")) |
            (AssetRegistry.public_ip_address.ilike(f"%{ip_address}%"))
        )

    asset = query.first()
    return _asset_to_dict(asset) if asset else None


# ── Delete ────────────────────────────────────────────────────────────────────
# UNCHANGED from original

def delete_asset(db: Session, asset_id: str) -> dict:
    asset = db.query(AssetRegistry).filter(AssetRegistry.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
    return {"message": "Asset deleted"}


def delete_all_assets(db: Session) -> dict:
    count = db.query(AssetRegistry).count()
    db.query(AssetRegistry).delete()
    db.commit()
    return {"message": f"Deleted {count} assets"}


def delete_bulk_assets(db: Session, asset_ids: List[str]) -> dict:
    deleted = 0
    for aid in asset_ids:
        asset = db.query(AssetRegistry).filter(AssetRegistry.id == aid).first()
        if asset:
            db.delete(asset)
            deleted += 1
    db.commit()
    return {"message": f"Deleted {deleted} assets"}


# ── Stats ─────────────────────────────────────────────────────────────────────
# UNCHANGED from original

def get_asset_stats(db: Session) -> dict:
    from sqlalchemy import func

    total      = db.query(AssetRegistry).count()
    running    = db.query(AssetRegistry).filter(AssetRegistry.power_state.ilike('running')).count()
    terminated = db.query(AssetRegistry).filter(AssetRegistry.power_state.ilike('terminated')).count()
    prod       = db.query(AssetRegistry).filter(AssetRegistry.environment.ilike('%prd%')).count()
    stg        = db.query(AssetRegistry).filter(AssetRegistry.environment.ilike('%stg%')).count()
    dev        = db.query(AssetRegistry).filter(AssetRegistry.environment.ilike('%dev%')).count()

    teams     = db.query(AssetRegistry.team, func.count(AssetRegistry.id)).group_by(AssetRegistry.team).all()
    verticals = db.query(AssetRegistry.team_verticals, func.count(AssetRegistry.id)).group_by(AssetRegistry.team_verticals).all()

    return {
        "total":       total,
        "running":     running,
        "terminated":  terminated,
        "by_env":      {"prd": prod, "stg": stg, "dev": dev},
        "by_team":     {t: c for t, c in teams if t},
        "by_vertical": {v: c for v, c in verticals if v},
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _asset_to_dict(asset: AssetRegistry) -> dict:
    return {
        "id":                             str(asset.id),
        "account_id":                     asset.account_id,
        "account_name":                   asset.account_name,
        "cloud_provider":                 asset.cloud_provider,
        "region":                         asset.region,
        "availability_zone":              asset.availability_zone,
        "instance_name":                  asset.instance_name,
        "vpc_name":                       asset.vpc_name,
        "vpc_id":                         asset.vpc_id,
        "private_ip_address":             asset.private_ip_address,
        "public_ip_address":              asset.public_ip_address,
        "application":                    asset.application,
        "environment":                    asset.environment,
        "team_verticals":                 asset.team_verticals,
        "team":                           asset.team,
        "contact_email":                  asset.contact_email,
        "engineering_dev_manager_email":  asset.engineering_dev_manager_email,
        "engineering_dev_director_email": asset.engineering_dev_director_email,
        "cloudops_manager_email":         asset.cloudops_manager_email,
        "cloudops_director_email":        asset.cloudops_director_email,
        "power_state":                    asset.power_state,
        "os_details":                     asset.os_details,
        "os_distribution":                asset.os_distribution,
        "is_active":                      asset.is_active,
        "uploaded_by":                    asset.uploaded_by,
        "created_at":                     asset.created_at.isoformat() if asset.created_at else None,
    }