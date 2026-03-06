"""
Middleware Service — Data Models

Data Privacy Design:
  - We NEVER store patient, doctor, or clinical data.
  - We ONLY store SaaS configuration: HMS connection URLs, API keys (encrypted),
    field mappings, hospital profile, and user accounts.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, DateTime, Enum as PgEnum, JSON, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


class HMSConnectionType(str, Enum):
    """Supported connection types to an existing HMS."""
    DATABASE = "database"       # Direct DB connection (most common — MySQL, MSSQL, PostgreSQL)
    REST_API = "rest_api"       # REST API endpoint
    HL7_FHIR = "hl7_fhir"      # Healthcare standard HL7/FHIR
    FILE_IMPORT = "file_import"  # CSV/Excel one-time import


class OnboardingStatus(str, Enum):
    PENDING = "pending"
    CONNECTING = "connecting"
    MAPPING = "mapping"        # Admin is reviewing field mappings
    ACTIVE = "active"
    FAILED = "failed"
    SUSPENDED = "suspended"


# ─── SaaS Tables (all that we store) ───────────────────────────────────────

class Hospital(Base):
    """
    Tenant record — one row per onboarded hospital.
    Contains ONLY SaaS metadata. No clinical data ever stored here.
    """
    __tablename__ = "hospitals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)       # URL-safe identifier
    contact_email = Column(String(200), nullable=False)
    country = Column(String(100), default="IN")
    timezone = Column(String(50), default="Asia/Kolkata")
    logo_url = Column(String(500), nullable=True)
    onboarding_status = Column(PgEnum(OnboardingStatus), default=OnboardingStatus.PENDING)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    users = relationship("User", back_populates="hospital")
    hms_connections = relationship("HMSConnection", back_populates="hospital")


class User(Base):
    """
    Platform users — super admins and hospital admins only.
    End users (patients/staff) are NOT stored here; they authenticate via HMS.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(300), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(String(50), nullable=False)         # super_admin | hospital_admin
    hospital_id = Column(UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    hospital = relationship("Hospital", back_populates="users")


class HMSConnection(Base):
    """
    Stores HOW to connect to a hospital's existing HMS.
    
    Data Privacy:
      - connection_config is stored encrypted at rest.
      - Contains ONLY connection metadata: URL, port, DB name, API endpoint.
      - API keys / passwords are stored encrypted, never in plaintext.
      - We NEVER pull or persist actual HMS records (patients, doctors, etc.).
    """
    __tablename__ = "hms_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id = Column(UUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    name = Column(String(200), nullable=False)           # e.g. "Main HMS", "Lab System"
    connection_type = Column(PgEnum(HMSConnectionType), nullable=False)
    
    # Encrypted JSON — stores: host, port, database, username, encrypted_password OR api_url, api_key_encrypted
    connection_config = Column(JSON, nullable=False, default=dict)
    
    is_verified = Column(Boolean, default=False)         # True once we've successfully pinged the HMS
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    hospital = relationship("Hospital", back_populates="hms_connections")
    field_mappings = relationship("FieldMapping", back_populates="connection")


class FieldMapping(Base):
    """
    Maps HMS field names to our internal schema.
    e.g. HMS column 'pat_nm' → our schema 'patient_name'
    
    This is SCHEMA METADATA — no actual patient records are stored.
    Used by the adapter engine to know how to translate data on-the-fly.
    """
    __tablename__ = "field_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("hms_connections.id"), nullable=False)
    entity_type = Column(String(100), nullable=False)       # e.g. "patient", "appointment"
    hms_table = Column(String(200), nullable=True)           # e.g. "tbl_patients"
    hms_field = Column(String(200), nullable=False)          # e.g. "pat_nm"
    our_field = Column(String(200), nullable=False)          # e.g. "patient_name"
    data_type = Column(String(50), default="string")         # string, integer, date, boolean
    transform = Column(Text, nullable=True)                   # Optional transform expression
    is_ai_suggested = Column(Boolean, default=False)         # Was this suggested by the AI mapper?
    is_confirmed = Column(Boolean, default=False)             # Admin confirmed this mapping?
    created_at = Column(DateTime(timezone=True), default=utcnow)

    connection = relationship("HMSConnection", back_populates="field_mappings")


class AuditLog(Base):
    """
    Immutable audit trail of all admin actions.
    Privacy: Only logs WHO did WHAT action, not the data content.
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    hospital_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(200), nullable=False)              # e.g. "hms_connection.created"
    resource_type = Column(String(100), nullable=True)        # e.g. "HMSConnection"
    resource_id = Column(String(200), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    metadata = Column(JSON, nullable=True, default=dict)      # Non-sensitive action context
    created_at = Column(DateTime(timezone=True), default=utcnow)
