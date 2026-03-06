import uuid
from sqlalchemy import Column, String, JSON, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from shared.db.connection import Base

class Hospital(Base):
    __tablename__ = "hospitals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    integration_config = relationship("IntegrationConfig", back_populates="hospital", uselist=False)

class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hospital_id = Column(UUID(as_uuid=True), ForeignKey("hospitals.id"), unique=True)
    source_type = Column(String, nullable=False) # 'database', 'api', 'file', 'hl7'
    connection_details = Column(JSON, nullable=False) # { "url": "...", "username": "..." }
    capabilities = Column(JSON, nullable=True) # E.g., { "appointment_scheduling": {"steps": [{"endpoint": "..."}]} }
    is_active = Column(Boolean, default=True)
    
    hospital = relationship("Hospital", back_populates="integration_config")
    field_mappings = relationship("FieldMapping", back_populates="config")

class FieldMapping(Base):
    __tablename__ = "field_mappings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), ForeignKey("integration_configs.id"))
    hms_field = Column(String, nullable=False)
    standard_field = Column(String, nullable=False)
    transformation_rules = Column(JSON, nullable=True) 
    
    config = relationship("IntegrationConfig", back_populates="field_mappings")
