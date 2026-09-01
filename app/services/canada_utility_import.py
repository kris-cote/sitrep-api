from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlmodel import Session, select
from app.models.infrastructure import InfrastructureFeature

DEFAULT_TIMEOUT_SECONDS = 30.0
NB_UTILITIES_GEOJSON = "https://gnb.socrata.com/api/geospatial/y3vu-vr3p?method=export&format=GeoJSON"
ON_UTILITY_LINE_QUERY = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open05/MapServer/11/query"
AB_POWERLINE_QUERY = "https://geospatial.alberta.ca/titan/rest/services/utility/access_utility/MapServer/15/query"

UTILITY_COVERAGE: Dict[str, Dict[str, Any]] = {
 "AB":{"status":"supported","source":"Government of Alberta Base Features Access Powerline","adapter":"ab-powerline","note":"Authoritative provincial powerline representation; source metadata retained."},
 "BC":{"status":"supported","source":"Government of British Columbia public transmission lines","adapter":"bc-transmission"},
 "NB":{"status":"supported","source":"Government of New Brunswick Utilities","adapter":"nb-utilities"},
 "ON":{"status":"supported_planning_context","source":"Ontario Utility Line / Land Information Ontario","adapter":"on-utility-line","note":"Historical linework is explicitly planning context."},
 "MB":{"status":"available_source_validation","source":"Manitoba 1:20,000 Utility Lines / Data MB","adapter":"adapter_pending","note":"Classified utility-line source confirmed; current machine-queryable provincial endpoint still being validated."},
 "SK":{"status":"geohub_validation","source":"Saskatchewan GeoHub","adapter":"adapter_pending","note":"Provincial GeoHub confirmed; authoritative province-wide utility layer endpoint still being validated."},
 "QC":{"status":"partial_public","source":"Données Québec / municipal transmission-line datasets","adapter":"adapter_pending"},
 "NL":{"status":"source_validation_required","adapter":"pending"},"NS":{"status":"source_validation_required","adapter":"pending"},"NT":{"status":"source_validation_required","adapter":"pending"},"NU":{"status":"source_validation_required","adapter":"pending"},"PE":{"status":"source_validation_required","adapter":"pending"},"YT":{"status":"source_validation_required","adapter":"pending"}}

class CanadaUtilityImportError(RuntimeError): pass

def utility_coverage(): return UTILITY_COVERAGE

def _centroid(geometry):
 points=[]
 def walk(v):
  if isinstance(v,(list,tuple)):
   if len(v)>=2 and isinstance(v[0],(int,float)) and isinstance(v[1],(int,float)): points.append((float(v[0]),float(v[1])))
   else:
    for x in v: walk(x)
 walk(geometry.get("coordinates") or [])
 return (None,None) if not points else (sum(p[1] for p in points)/len(points),sum(p[0] for p in points)/len(points))

def _upsert(session,p):
 e=session.exec(select(InfrastructureFeature).where(InfrastructureFeature.tenant_id==p["tenant_id"]).where(InfrastructureFeature.source_system==p["source_system"]).where(InfrastructureFeature.source_id==p["source_id"])).first()
 if e:
  for k in ("category","subtype","name","geometry_type","geometry","centroid_latitude","centroid_longitude","criticality_score","vulnerability_score","source_url","properties"): setattr(e,k,p[k])
  e.updated_at=datetime.now(timezone.utc); session.add(e); return False
 session.add(InfrastructureFeature(**p)); return True

def _classify(text):
 t=text.lower()
 if any(x in t for x in ("hydro","power","electric","transmission")): return "electric","transmission_line",.88
 if any(x in t for x in ("communication","telecom","fibre","fiber")): return "telecom","communications_line",.78
 if "water" in t: return "water","water_pipeline",.80
 if any(x in t for x in ("natural gas","gas","fuel","pipeline")): return "fuel","pipeline",.82
 return "utility","utility_line",.65

def _base(feature,tenant,category,subtype,name,crit,system,prefix,url,extra):
 g=feature.get("geometry") or {}; props=dict(feature.get("properties") or {})
 if not g:return None
 lat,lon=_centroid(g); rid=feature.get("id") or props.get("OBJECTID") or props.get("objectid") or props.get("GLOBALID") or f"{g.get('type')}:{hash(str(g))}"
 return {"tenant_id":tenant,"category":category,"subtype":subtype,"name":name,"geometry_type":str(g.get("type") or "Unknown"),"geometry":g,"centroid_latitude":lat,"centroid_longitude":lon,"criticality_score":crit,"vulnerability_score":.5,"source_system":system,"source_id":f"{prefix}:{rid}","source_url":url,"properties":extra|{"public_attributes":props}}

def normalize_nb_utility(feature,tenant_id="default"):
 props=feature.get("properties") or {}; c,s,k=_classify(" ".join(str(v) for v in props.values() if v is not None)); return _base(feature,tenant_id,c,s,str(props.get("name") or props.get("NAME") or f"New Brunswick {s}"),k,"NB-OpenData-Utilities","NB-UTIL",NB_UTILITIES_GEOJSON,{"jurisdiction":"NB","source_dataset":"Government of New Brunswick Utilities"})

def normalize_on_utility(feature,tenant_id="default"):
 props=feature.get("properties") or {}; c,s,k=_classify(" ".join(str(v) for v in props.values() if v is not None)); label=props.get("UTILITY_LINE_TYPE") or props.get("UTILITY_TYPE") or props.get("FEATURE_TYPE") or props.get("TYPE") or f"Ontario {s}"; return _base(feature,tenant_id,c,s,str(label),k,"Ontario-LIO-UtilityLine","ON-UTIL",ON_UTILITY_LINE_QUERY,{"jurisdiction":"ON","source_dataset":"Ontario Utility Line","planning_context_only":True,"source_last_updated":"2013-07-02","source_data_range_end":"2008-06-12","freshness_warning":"Historical/open planning context; not authoritative current operational topology."})

def normalize_ab_powerline(feature,tenant_id="default"):
 item=_base(feature,tenant_id,"electric","powerline","Alberta Powerline",.86,"AB-BaseFeatures-Powerline","AB-POWER",AB_POWERLINE_QUERY,{"jurisdiction":"AB","source_dataset":"Government of Alberta Base Features Access Powerline","authoritative_source":True})
 if item: item["properties"]["public_attributes"]={k:v for k,v in item["properties"]["public_attributes"].items() if str(k).upper() not in {"VOLTAGE","KV","CAPACITY"}}
 return item

async def _fetch(url,params=None,user_agent="SitRep/3.3 UtilityImporter"):
 try:
  async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS,follow_redirects=True) as client:
   r=await client.get(url,params=params,headers={"User-Agent":user_agent}); r.raise_for_status(); data=r.json()
 except (httpx.HTTPError,ValueError) as exc: raise CanadaUtilityImportError(str(exc)) from exc
 if isinstance(data,dict) and data.get("error"): raise CanadaUtilityImportError(str(data["error"]))
 return data

def _persist(session,features,normalizer,tenant):
 created=updated=skipped=0; by={}
 for f in features:
  item=normalizer(f,tenant)
  if not item: skipped+=1; continue
  new=_upsert(session,item); created+=int(new); updated+=int(not new); by[item["subtype"]]=by.get(item["subtype"],0)+1
 session.commit(); return created,updated,skipped,by

async def import_nb_utilities(session,tenant_id="default",limit=5000):
 data=await _fetch(NB_UTILITIES_GEOJSON); fs=list(data.get("features") or [])[:max(1,min(limit,5000))]; c,u,s,b=_persist(session,fs,normalize_nb_utility,tenant_id); return {"source":"Government of New Brunswick Utilities","jurisdiction":"NB","created":c,"updated":u,"skipped":s,"fetched":len(fs),"by_subtype":b}

async def import_on_utilities(session,tenant_id="default",bbox=None,limit=5000):
 p={"f":"geojson","where":"1=1","outFields":"*","returnGeometry":"true","outSR":"4326","resultRecordCount":max(1,min(limit,5000))}
 if bbox:
  x=[float(v.strip()) for v in bbox.split(",")]
  if len(x)!=4: raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
  p.update({"geometry":",".join(str(v) for v in x),"geometryType":"esriGeometryEnvelope","inSR":"4326","spatialRel":"esriSpatialRelIntersects"})
 data=await _fetch(ON_UTILITY_LINE_QUERY,p); fs=list(data.get("features") or []); c,u,s,b=_persist(session,fs,normalize_on_utility,tenant_id); return {"source":"Ontario Utility Line / Land Information Ontario","jurisdiction":"ON","created":c,"updated":u,"skipped":s,"fetched":len(fs),"by_subtype":b,"planning_context_only":True,"freshness_warning":"Historical source; not current operational topology."}

async def import_ab_powerlines(session,tenant_id="default",bbox=None,limit=1000):
 p={"where":"1=1","outFields":"OBJECTID,FEATURE_TYPE,GEO_SOURCE,GEO_DATE,FEATURE_TYPE_SOURCE,FEATURE_TYPE_DATE,GLOBALID,UPDATE_DATE","returnGeometry":"true","outSR":4326,"f":"geojson","resultRecordCount":max(1,min(limit,1000))}
 if bbox:
  x=[float(v.strip()) for v in bbox.split(",")]
  if len(x)!=4: raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
  p.update({"geometry":",".join(str(v) for v in x),"geometryType":"esriGeometryEnvelope","inSR":4326,"spatialRel":"esriSpatialRelIntersects"})
 data=await _fetch(AB_POWERLINE_QUERY,p); fs=list(data.get("features") or []); c,u,s,b=_persist(session,fs,normalize_ab_powerline,tenant_id); return {"source":"Government of Alberta Base Features Access Powerline","jurisdiction":"AB","created":c,"updated":u,"skipped":s,"fetched":len(fs),"by_subtype":b,"planning_context_only":False}
