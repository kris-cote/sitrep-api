from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select
from app.models.db import get_session
from app.models.infrastructure import InfrastructureFeature
from app.services.bc_infrastructure_import import BCInfrastructureImportError, DEFAULT_VANCOUVER_ISLAND_BBOX, import_bc_infrastructure
from app.services.canada_infrastructure_import import CanadaInfrastructureImportError, import_nrn_major_roads, national_infrastructure_coverage
from app.services.canada_rail_import import CanadaRailImportError, import_nrwn_rail
from app.services.canada_utility_import import CanadaUtilityImportError, import_ab_powerlines, import_nb_utilities, import_on_utilities, utility_coverage
router=APIRouter(prefix="/infrastructure",tags=["infrastructure"])
PUBLIC_SOURCE_CATALOG={"canada-national-road-network":{"category":"transport","subtype":"road","publisher":"Statistics Canada / GeoBase","coverage":"All provinces and territories"},"canada-national-railway-network":{"category":"transport","subtype":"railway","publisher":"NRCan / Transport Canada / GeoBase"},"bc-transmission-lines":{"category":"electric","subtype":"transmission_line","publisher":"Government of British Columbia"},"ab-powerlines":{"category":"electric","subtype":"powerline","publisher":"Government of Alberta","dataset":"Base Features Access Powerline","note":"Authoritative provincial representation; public attributes only."},"nb-utilities":{"category":"utility","subtype":"mixed","publisher":"Government of New Brunswick"},"on-utility-line":{"category":"utility","subtype":"mixed","publisher":"Government of Ontario / Land Information Ontario","note":"Historical planning context."}}
class InfrastructureCreate(BaseModel):
 tenant_id:str="default"; category:str; subtype:str="general"; name:str="Unnamed feature"; geometry:Dict[str,Any]; centroid_latitude:Optional[float]=None; centroid_longitude:Optional[float]=None; criticality_score:float=PydanticField(default=.5,ge=0,le=1); vulnerability_score:float=PydanticField(default=.5,ge=0,le=1); source_system:str="manual"; source_id:Optional[str]=None; source_url:Optional[str]=None; properties:Dict[str,Any]={}
@router.get("/sources")
def sources(): return PUBLIC_SOURCE_CATALOG
@router.get("/coverage/canada")
def coverage(): return national_infrastructure_coverage()
@router.get("/coverage/canada/utilities")
def util_coverage(): return utility_coverage()
@router.post("/canada/roads/import")
async def roads(jurisdiction:str=Query(...,min_length=2,max_length=2),bbox:Optional[str]=None,tenant_id:str="default",limit:int=Query(2000,ge=1,le=2000),session:Session=Depends(get_session)):
 try:return await import_nrn_major_roads(session=session,jurisdiction=jurisdiction,tenant_id=tenant_id,bbox=bbox,limit=limit)
 except ValueError as e:raise HTTPException(400,detail=str(e))
 except CanadaInfrastructureImportError as e:raise HTTPException(502,detail={"upstream":"Statistics Canada NRN","error":str(e)})
@router.post("/canada/rail/import")
async def rail(jurisdiction:str=Query(...,min_length=2,max_length=2),tenant_id:str="default",limit:int=Query(5000,ge=1,le=5000),session:Session=Depends(get_session)):
 try:return await import_nrwn_rail(session=session,jurisdiction=jurisdiction,tenant_id=tenant_id,limit=limit)
 except ValueError as e:raise HTTPException(400,detail=str(e))
 except CanadaRailImportError as e:raise HTTPException(502,detail={"upstream":"NRCan NRWN","error":str(e)})
@router.post("/canada/utilities/ab/import")
async def ab_utilities(bbox:Optional[str]=Query(None,description="Optional minLon,minLat,maxLon,maxLat"),tenant_id:str="default",limit:int=Query(1000,ge=1,le=1000),session:Session=Depends(get_session)):
 try:return await import_ab_powerlines(session=session,tenant_id=tenant_id,bbox=bbox,limit=limit)
 except ValueError as e:raise HTTPException(400,detail=str(e))
 except CanadaUtilityImportError as e:raise HTTPException(502,detail={"upstream":"Government of Alberta Powerlines","error":str(e)})
@router.post("/canada/utilities/nb/import")
async def nb_utilities(tenant_id:str="default",limit:int=Query(5000,ge=1,le=5000),session:Session=Depends(get_session)):
 try:return await import_nb_utilities(session=session,tenant_id=tenant_id,limit=limit)
 except CanadaUtilityImportError as e:raise HTTPException(502,detail={"upstream":"Government of New Brunswick Utilities","error":str(e)})
@router.post("/canada/utilities/on/import")
async def on_utilities(bbox:Optional[str]=None,tenant_id:str="default",limit:int=Query(5000,ge=1,le=5000),session:Session=Depends(get_session)):
 try:return await import_on_utilities(session=session,tenant_id=tenant_id,bbox=bbox,limit=limit)
 except ValueError as e:raise HTTPException(400,detail=str(e))
 except CanadaUtilityImportError as e:raise HTTPException(502,detail={"upstream":"Ontario Utility Line / LIO","error":str(e)})
@router.post("/bc/import")
async def bc_import(datasets:str="roads,rail,transmission",bbox:str=DEFAULT_VANCOUVER_ISLAND_BBOX,tenant_id:str="default",limit_per_dataset:int=Query(1000,ge=1,le=1000),session:Session=Depends(get_session)):
 try:return await import_bc_infrastructure(session=session,datasets=[x.strip() for x in datasets.split(",") if x.strip()],tenant_id=tenant_id,bbox=bbox,limit_per_dataset=limit_per_dataset)
 except ValueError as e:raise HTTPException(400,detail=str(e))
 except BCInfrastructureImportError as e:raise HTTPException(502,detail={"upstream":"BC DataBC ArcGIS","error":str(e)})
@router.post("",status_code=201)
def create(payload:InfrastructureCreate,session:Session=Depends(get_session)):
 item=InfrastructureFeature(**payload.model_dump(),geometry_type=str(payload.geometry.get("type") or "Unknown"),updated_at=datetime.now(timezone.utc));session.add(item);session.commit();session.refresh(item);return item
@router.get("")
def list_items(tenant_id:str="default",category:Optional[str]=None,subtype:Optional[str]=None,limit:int=Query(200,ge=1,le=2000),session:Session=Depends(get_session)):
 q=select(InfrastructureFeature).where(InfrastructureFeature.tenant_id==tenant_id)
 if category:q=q.where(InfrastructureFeature.category==category)
 if subtype:q=q.where(InfrastructureFeature.subtype==subtype)
 return list(session.exec(q.order_by(InfrastructureFeature.updated_at.desc()).limit(limit)).all())
@router.get("/{feature_id}")
def get_item(feature_id:str,session:Session=Depends(get_session)):
 item=session.get(InfrastructureFeature,feature_id)
 if not item:raise HTTPException(404,detail="Infrastructure feature not found")
 return item
