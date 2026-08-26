from pathlib import Path
import pandas as pd
import numpy as np

R=Path(__file__).resolve().parents[2]
v=pd.read_csv(R/'data/processed/vegetation/mod13q1_v061_district_2015-01-01_2025-12-31.csv')
v['date']=pd.to_datetime(v.date)
v=v.sort_values(['district_id','date'])
v['target_date']=v.groupby('district_id').date.shift(-1)
v['target']=v.groupby('district_id').ndvi_anomaly_z.shift(-1).le(-1)
v['known']=v.groupby('district_id').ndvi_anomaly_z.shift(-1).notna()
print('DROUGHT',len(v[v.known]),v.loc[v.known,'target'].value_counts().to_dict())
print(pd.crosstab(v.loc[v.known,'target_date'].dt.year,v.loc[v.known,'target']))

r=pd.read_csv(R/'data/processed/river_levels/river_levels_canonical.csv')
m=pd.read_csv(R/'data/processed/river_station_metadata.csv')
r['date']=pd.to_datetime(r.date); r=r[r.date.between('2015-01-01','2025-12-31')]
r=r.merge(m[['station_code','moderate_threshold_m','high_threshold_m']],left_on='station_id',right_on='station_code')
r=r.sort_values(['station_id','date']).drop_duplicates(['station_id','date'],keep='last')
for h in [1,3,7]:
  vals=[]
  for station,g in r.groupby('station_id'):
    s=g.set_index('date').level_m
    fut=pd.concat([s.shift(-i) for i in range(1,h+1)],axis=1).max(axis=1)
    valid=pd.concat([s.shift(-i) for i in range(1,h+1)],axis=1).notna().all(axis=1)
    y=(fut>=g.set_index('date').moderate_threshold_m).where(valid)
    q=pd.DataFrame({'y':y,'year':y.index.year}); q['station']=station; vals.append(q)
  q=pd.concat(vals)
  print('FLOOD',h,int(q.y.notna().sum()),q.y.value_counts().to_dict())
  print(pd.crosstab([q.station,q.year],q.y).tail(30))

i=pd.read_csv(R/'data/processed/food_security/ipc_outcomes_canonical.csv')
print('IPC sources',i.source_file.value_counts().to_dict())
print('IPC types',i.assessment_period_type.value_counts().to_dict(),'phases',i.Phase.astype(str).value_counts().head(12).to_dict())
x=i[(i.source_file.str.contains('level1',case=False,na=False))&(i.assessment_period_type.eq('current'))&(i.Phase.astype(str).eq('3+'))].copy()
x['From']=pd.to_datetime(x['From']); x['Percentage']=pd.to_numeric(x.Percentage,errors='coerce')
print('FOOD rows',len(x),'regions',x['Level 1'].nunique(),'assessments',x['From'].nunique(),'range',x['From'].min(),x['From'].max())
print('dupes',x.duplicated(['Level 1','From']).sum())
for cutoff in [.1,.15,.2,.25,.3]: print('cut',cutoff,(x.Percentage>=cutoff).value_counts().to_dict())
print(pd.crosstab(x.From.dt.year,x.Percentage>=.2))
